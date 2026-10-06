"""src/distill.py end to end on a made-up document with hand-made vectors."""
import json

import numpy as np
import pytest

from src import distill, state

TEXTS = [
    "oil the gate hinge",           # 1  same thing as 2
    "oil the gate hinge today",     # 2
    "fix the gate latch",           # 3  same theme as 1-2
    "renew the library card",       # 4  same theme as 5
    "return the library books",     # 5
    "learn the accordion",          # 6  close to nothing
]
VECTORS = np.array([
    [1, 0, 0, 0], [1, 0, 0, 0], [0.6, 0.8, 0, 0],
    [0, 0, 1, 0], [0, 0, 0.6, 0.8],
    [0, -0.6, 0, -0.8],
])


@pytest.fixture
def root(tmp_path):
    doc = tmp_path / "doc-1"
    (doc / "work").mkdir(parents=True)
    (doc / "items.jsonl").write_text(
        "".join(json.dumps({"n": n, "text": t, "detail": None}) + "\n" for n, t in enumerate(TEXTS, 1)))
    np.save(doc / "work" / "vectors.npy", VECTORS)
    return tmp_path


def run(root, capsys, *argv):
    code = distill.main(["--root", str(root), *argv])
    return code, json.loads(capsys.readouterr().out)


def test_propose_writes_both_levels_and_starts_the_log(root, capsys):
    code, out = run(root, capsys, "propose", "doc-1")
    assert code == 0
    assert out == {
        "items": 6, "groups": 1, "items_in_groups": 2, "largest_group": 2,
        "themes": 2, "items_in_themes": 5, "largest_theme": 3, "items_in_no_theme": 1,
    }
    proposal = json.loads((root / "doc-1" / "work" / "proposal.json").read_text())
    assert [g["items"] for g in proposal["groups"]] == [[1, 2]]
    assert [t["items"] for t in proposal["themes"]] == [[1, 2, 3], [4, 5]]
    assert proposal["settings"]["same_cut"] == 0.25
    log = state.read_log(root / "doc-1" / "work" / "log.jsonl")
    assert [(e["who"], e["op"], e.get("groups"), e["items"]) for e in log] == [
        ("proposal", "create", None, [1, 2]),
        ("proposal", "theme", ["g1"], [3]),
        ("proposal", "theme", [], [4, 5]),
    ]
    assert log[0]["name"] in TEXTS[:2] and log[1]["name"] in TEXTS[:3]

    code, out = run(root, capsys, "status", "doc-1")
    assert (out["in_groups"], out["undecided"], out["proposed"]) == (2, 4, True)
    assert (out["themes"], out["in_no_theme"]) == (2, 1)


def test_propose_refuses_to_replace_a_proposal(root, capsys):
    run(root, capsys, "propose", "doc-1")
    code, out = run(root, capsys, "propose", "doc-1")
    assert code == 1 and "Move it away first" in out["error"]


def test_propose_needs_vectors_for_every_item(root, capsys):
    np.save(root / "doc-1" / "work" / "vectors.npy", VECTORS[:5])
    code, out = run(root, capsys, "propose", "doc-1")
    assert code == 1 and "5 vectors for 6 items" in out["error"]
    assert not (root / "doc-1" / "work" / "proposal.json").exists()


def test_groups_lists_oldest_first_and_can_leave_out_reviewed_ones(root, capsys):
    run(root, capsys, "propose", "doc-1")
    _, out = run(root, capsys, "groups", "doc-1")
    assert (out["total"], out["shown"]) == (1, 1)
    g = out["groups"][0]
    assert (g["group"], g["size"], g["oldest"], g["span"], g["confirmed"]) == ("g1", 2, 2, [1, 2], False)
    assert g["sample"] == [TEXTS[1], TEXTS[0]]

    state.append(root / "doc-1", {"who": "agent", "op": "draft", "group": "g1", "text": "Oil the gate hinge"})
    assert run(root, capsys, "groups", "doc-1", "--unreviewed")[1]["total"] == 0
    assert run(root, capsys, "groups", "doc-1")[1]["groups"][0]["draft"] == "Oil the gate hinge"


def test_themes_are_paged_largest_first(root, capsys):
    run(root, capsys, "propose", "doc-1")
    _, out = run(root, capsys, "themes", "doc-1", "--limit", "1")
    assert (out["total"], out["shown"]) == (2, 1)
    name = out["themes"][0].pop("name")
    assert name in TEXTS[:3]
    assert out["themes"][0] == {
        "theme": "t1", "size": 3, "groups": 1, "oldest": 3, "span": [1, 3], "undecided": 1,
        "confirmed": False, "sample": [TEXTS[2], TEXTS[1], TEXTS[0]],
    }
    _, out = run(root, capsys, "themes", "doc-1", "--limit", "1", "--offset", "1")
    assert out["themes"][0]["theme"] == "t2"


def test_show_gives_the_items_and_their_nearest_outside_neighbours(root, capsys):
    run(root, capsys, "propose", "doc-1")
    _, out = run(root, capsys, "show", "doc-1", "g1")
    assert [it["n"] for it in out["items"]] == [2, 1]
    assert out["nearest_outside"][0]["n"] == 3
    assert out["nearest_outside"][0]["where"] == "undecided"
    assert all(it["n"] not in (1, 2) for it in out["nearest_outside"])

    _, out = run(root, capsys, "show", "doc-1", "t1")
    assert [(it["n"], it["where"]) for it in out["items"]] == [(3, "undecided"), (2, "g1"), (1, "g1")]
    assert out["groups"] == ["g1"] and {it["theme"] for it in out["items"]} == {"t1"}
    assert {it["n"]: it["theme"] for it in out["nearest_outside"]}[6] is None

    state.append(root / "doc-1", {"who": "agent", "op": "assign", "item": 6, "theme": "t1"})
    _, out = run(root, capsys, "show", "doc-1", "t1")
    assert [it["n"] for it in out["items"]] == [6, 3, 2, 1]

    code, out = run(root, capsys, "show", "doc-1", "g99")
    assert code == 1 and "no group, theme or item 'g99'" in out["error"]


def test_long_text_is_cut(root, capsys):
    doc = root / "doc-1"
    rows = [json.loads(line) for line in (doc / "items.jsonl").read_text().splitlines()]
    rows[0]["text"] = "oil the gate hinge " * 20
    (doc / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    run(root, capsys, "propose", "doc-1")
    _, out = run(root, capsys, "show", "doc-1", "g1")
    assert max(len(it["text"]) for it in out["items"]) == distill.TEXT_CHARS


def test_show_on_an_item_suggests_a_split_only_when_it_has_several_sentences(root, capsys):
    doc = root / "doc-1"
    rows = [json.loads(line) for line in (doc / "items.jsonl").read_text().splitlines()]
    rows[5]["text"] = "Learn the accordion. Oil the gate hinge? Renew the library card"
    (doc / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    _, out = run(root, capsys, "show", "doc-1", "6")
    assert out["item"] == 6
    assert out["split"] == ["Learn the accordion.", "Oil the gate hinge?", "Renew the library card"]
    assert [it["n"] for it in out["items"]] == [6]
    assert 6 not in [it["n"] for it in out["nearest_outside"]]
    assert "split" not in run(root, capsys, "show", "doc-1", "1")[1]


@pytest.fixture
def embedded(root, monkeypatch):
    """Parts embed with a made-up function: the gate direction, or the library one."""
    calls = []

    def fake(model):
        assert model == "made-up-model"

        def embed(texts):
            calls.append(list(texts))
            return np.array([[1, 0, 0, 0] if "gate" in t else [0, 0, 1, 0] for t in texts], dtype=float)
        return embed

    (root / "doc-1" / "work" / "embed_summary.json").write_text(json.dumps({"model": "made-up-model"}))
    monkeypatch.setattr(distill, "fastembed_fn", fake)
    return calls


def test_break_makes_parts_that_show_among_their_neighbours(root, capsys, embedded):
    run(root, capsys, "propose", "doc-1")
    code, out = run(root, capsys, "break", "doc-1", "6", "--who", "owner", "oil the gate hinge again", "renew the library card too")
    assert code == 0
    assert out == {"item": 6, "parts": [
        {"n": "6.1", "text": "oil the gate hinge again"}, {"n": "6.2", "text": "renew the library card too"}]}
    _, out = run(root, capsys, "status", "doc-1")
    assert (out["broken"], out["parts"], out["undecided"]) == (1, 2, 5)

    _, out = run(root, capsys, "show", "doc-1", "6.1")
    assert out["item"] == "6.1" and out["items"][0]["where"] == "undecided"
    assert (out["nearest_outside"][0]["n"], out["nearest_outside"][0]["where"]) in ((1, "g1"), (2, "g1"))
    _, out = run(root, capsys, "show", "doc-1", "g1")
    assert out["nearest_outside"][0]["n"] == "6.1"
    assert 6 not in [it["n"] for it in out["nearest_outside"]]
    _, out = run(root, capsys, "show", "doc-1", "6")
    assert out["parts"] == ["6.1", "6.2"] and out["items"][0]["where"] == "broken"
    assert embedded == [["oil the gate hinge again", "renew the library card too"]]  # embedded once, then cached

    state.append(root / "doc-1", {"who": "agent", "op": "move", "item": "6.1", "group": "g1"})
    g = run(root, capsys, "groups", "doc-1")[1]["groups"][0]
    assert (g["size"], g["oldest"], g["span"]) == (3, "6.1", [1, "6.1"])
    assert g["sample"][0] == "oil the gate hinge again"


def test_break_is_refused_from_anyone_but_the_owner(root, capsys):
    code, out = run(root, capsys, "break", "doc-1", "6", "--who", "agent", "a", "b")
    assert code == 1 and "only the owner breaks" in out["error"]
    assert not (root / "doc-1" / "work" / "log.jsonl").read_text()


def test_parts_cannot_be_embedded_without_knowing_the_model(root, capsys):
    run(root, capsys, "break", "doc-1", "6", "--who", "owner", "a", "b")
    code, out = run(root, capsys, "show", "doc-1", "1")
    assert code == 1 and "model the items were embedded with is unknown" in out["error"]


def test_edits_append_one_line_each_and_number_new_groups_and_themes(root, capsys):
    run(root, capsys, "propose", "doc-1")  # g1 = 1, 2; t1 = g1 + 3; t2 = 4, 5
    doc = root / "doc-1"
    steps = [
        (("create", "doc-1", "library", "4", "5"), {"group": "g2", "items": [4, 5]}),
        (("theme", "doc-1", "paper", "g2", "6"), {"theme": "t3", "groups": ["g2"], "items": [6]}),
        (("split", "doc-1", "g2", "books", "5"), {"new": "g3", "items": [5]}),
        (("rename", "doc-1", "g3", "library books"), {"group": "g3"}),
        (("rename", "doc-1", "t3", "desk"), {"theme": "t3"}),
        (("merge", "doc-1", "g2", "g3"), {"into": "g2", "groups": ["g3"]}),
        (("move", "doc-1", "3", "g1"), {"item": 3}),
        (("draft", "doc-1", "g1", "Fix the gate"), {"text": "Fix the gate"}),
        (("flag", "doc-1", "g1", "latch too?"), {"note": "latch too?"}),
        (("keep", "doc-1", "6"), {"item": 6}),
        (("assign", "doc-1", "6", "none"), {"item": 6, "theme": None}),
        (("assign", "doc-1", "g2", "t1"), {"group": "g2", "theme": "t1"}),
        (("drop", "doc-1", "6", "not this year"), {"reason": "not this year"}),
        (("undo", "doc-1"), {}),
        (("unassign", "doc-1", "6"), {"item": 6}),
        (("create", "doc-1", "again", "6"), {"group": "g4"}),  # g3 was merged away; its id is not reused
    ]
    for argv, fields in steps:
        code, out = run(root, capsys, *argv)
        assert code == 0, out
        assert out["logged"]["who"] == "agent" and out["logged"]["op"] == argv[0]
        assert fields.items() <= out["logged"].items()
    st, _ = state.load(doc)
    assert {gid: g["items"] for gid, g in st["groups"].items()} == {"g1": [1, 2, 3], "g2": [4, 5], "g4": [6]}
    assert st["themes"] == {"t1": {"name": st["themes"]["t1"]["name"], "groups": ["g1", "g2"], "items": [], "confirmed": False}}
    assert len(state.read_log(doc / "work" / "log.jsonl")) == 3 + len(steps)

    code, out = run(root, capsys, "fold", "doc-1", "t1", "t9")
    assert code == 1 and "no theme 't9'" in out["error"]
    code, out = run(root, capsys, "keep", "doc-1", "g1")
    assert code == 1 and "not an item: 'g1'" in out["error"]
    assert len(state.read_log(doc / "work" / "log.jsonl")) == 3 + len(steps)


def test_export_writes_confirmed_groups_and_kept_items_by_theme(root, capsys):
    run(root, capsys, "propose", "doc-1")
    doc = root / "doc-1"
    run(root, capsys, "draft", "doc-1", "g1", "Oil the gate hinge")
    run(root, capsys, "keep", "doc-1", "3")
    run(root, capsys, "keep", "doc-1", "5")
    run(root, capsys, "drop", "doc-1", "6", "not this year")
    code, out = run(root, capsys, "export", "doc-1")
    assert code == 0
    assert {k: v for k, v in out.items() if k != "wrote"} == {
        "lines": 2, "sections": 2, "dropped": 1, "undecided": 1, "groups_not_confirmed": 1}
    md = (doc / "work" / "distilled.md").read_text()
    assert "Oil the gate hinge" not in md and "- fix the gate latch [1]" in md
    assert "- 6: learn the accordion — not this year" in md
    assert "1 groups not confirmed (left out" in md

    state.append(doc, {"who": "owner", "op": "confirm", "group": "g1"})
    run(root, capsys, "export", "doc-1")
    lines = (doc / "work" / "distilled.md").read_text().splitlines()
    t1 = state.load(doc)[0]["themes"]["t1"]["name"]
    start = lines.index(f"## {t1}")
    assert lines[start + 2 : start + 4] == ["- fix the gate latch [1]", "- Oil the gate hinge [2]"]  # oldest first
    assert lines[lines.index("**[2]** Oil the gate hinge") + 2 :][:2] == ["- 2: oil the gate hinge today", "- 1: oil the gate hinge"]

    state.append(doc, {"who": "agent", "op": "rename", "group": "g1", "name": "gate"})
    code, out = run(root, capsys, "export", "doc-1", "--draft")
    assert out["lines"] == 3 and "- Oil the gate hinge (not confirmed) [2]" in (doc / "work" / "distilled.md").read_text()
