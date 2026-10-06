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
    assert [(e["who"], e["op"], e["items"]) for e in log] == [("proposal", "create", [1, 2])]
    assert log[0]["name"] in TEXTS[:2]

    code, out = run(root, capsys, "status", "doc-1")
    assert (out["in_groups"], out["undecided"], out["proposed"]) == (2, 4, True)


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
    assert out["themes"][0] == {
        "theme": "t1", "size": 3, "oldest": 3, "span": [1, 3], "undecided": 1,
        "sample": [TEXTS[2], TEXTS[1], TEXTS[0]],
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

    code, out = run(root, capsys, "show", "doc-1", "g99")
    assert code == 1 and "no group or theme 'g99'" in out["error"]


def test_long_text_is_cut(root, capsys):
    doc = root / "doc-1"
    rows = [json.loads(line) for line in (doc / "items.jsonl").read_text().splitlines()]
    rows[0]["text"] = "oil the gate hinge " * 20
    (doc / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    run(root, capsys, "propose", "doc-1")
    _, out = run(root, capsys, "show", "doc-1", "g1")
    assert max(len(it["text"]) for it in out["items"]) == distill.TEXT_CHARS
