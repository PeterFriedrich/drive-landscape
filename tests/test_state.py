"""src/state.py: the decision log, its replay, and the accounted-for check. Made-up items only."""
import json

import pytest

from src.state import LogError, account, append, load, read_log, replay

NS = [1, 2, 3, 4, 5, 6]


def agent(op, **fields):
    return {"who": "agent", "op": op, **fields}


def owner(op, **fields):
    return {"who": "owner", "op": op, **fields}


BASE = [
    agent("create", group="g1", name="garden", items=[1, 2, 3]),
    agent("create", group="g2", name="paperwork", items=[4]),
    agent("keep", item=5),
]


def test_empty_log_leaves_everything_undecided():
    state = replay(NS, [])
    assert state["undecided"] == set(NS)
    assert account(NS, state) == {
        "items": 6, "in_groups": 0, "kept": 0, "dropped": 0, "undecided": 6, "broken": 0, "parts": 0,
        "groups": 0, "groups_confirmed": 0, "groups_flagged": 0, "kept_confirmed": 0, "later": 0,
        "themes": 0, "themes_confirmed": 0, "in_no_theme": 6,
    }


def test_create_keep_drop_place_each_item_once():
    state = replay(NS, BASE + [agent("drop", item=6, reason="duplicate of another list")])
    assert state["groups"]["g1"]["items"] == [1, 2, 3]
    assert state["groups"]["g1"]["name"] == "garden"
    assert set(state["kept"]) == {5}
    assert state["dropped"] == {6: "duplicate of another list"}
    assert state["undecided"] == set()
    assert account(NS, state)["in_groups"] == 4


def test_move_keep_drop_and_unassign_take_the_item_from_where_it_was():
    state = replay(NS, BASE + [
        agent("move", item=3, group="g2"),
        agent("keep", item=2),
        agent("drop", item=5, reason="no longer wanted"),
        agent("unassign", item=4),
    ])
    assert state["groups"]["g1"]["items"] == [1]
    assert state["groups"]["g2"]["items"] == [3]
    assert set(state["kept"]) == {2}
    assert set(state["dropped"]) == {5}
    assert state["undecided"] == {4, 6}
    account(NS, state)


def test_a_group_that_loses_its_last_item_is_gone():
    state = replay(NS, BASE + [agent("keep", item=4)])
    assert "g2" not in state["groups"]


def test_merge_and_split():
    state = replay(NS, BASE + [
        agent("merge", into="g1", groups=["g2"]),
        agent("split", group="g1", items=[1, 4], new="g3", name="shed"),
    ])
    assert set(state["groups"]) == {"g1", "g3"}
    assert state["groups"]["g1"]["items"] == [2, 3]
    assert state["groups"]["g3"] == {
        "name": "shed", "items": [1, 4], "draft": None, "flag": None, "later": False, "confirmed": False,
    }


def test_rename_draft_flag():
    state = replay(NS, BASE + [
        agent("rename", group="g1", name="yard"),
        agent("draft", group="g1", text="Sort out the yard"),
        agent("flag", group="g1", note="two of these may be different jobs"),
    ])
    g = state["groups"]["g1"]
    assert (g["name"], g["draft"], g["flag"]) == ("yard", "Sort out the yard", "two of these may be different jobs")
    assert account(NS, state)["groups_flagged"] == 1


def test_only_the_owner_confirms():
    with pytest.raises(LogError, match="line 4: confirm: only the owner confirms"):
        replay(NS, BASE + [agent("confirm", group="g1")])
    state = replay(NS, BASE + [
        agent("flag", group="g1", note="check"),
        owner("confirm", group="g1"),
        owner("confirm", item=5),
    ])
    assert state["groups"]["g1"]["confirmed"] is True
    assert state["groups"]["g1"]["flag"] is None
    counts = account(NS, state)
    assert (counts["groups_confirmed"], counts["kept_confirmed"]) == (1, 1)


@pytest.mark.parametrize("edit", [
    agent("move", item=4, group="g1"),
    agent("keep", item=1),
    agent("rename", group="g1", name="yard"),
    agent("draft", group="g1", text="Sort out the yard"),
    agent("merge", into="g1", groups=["g2"]),
    agent("split", group="g1", items=[1], new="g3", name="shed"),
])
def test_changing_a_confirmed_group_unconfirms_it(edit):
    state = replay(NS, BASE + [owner("confirm", group="g1"), edit])
    assert state["groups"]["g1"]["confirmed"] is False


def test_undo_ignores_the_line_before_it():
    state = replay(NS, BASE + [agent("drop", item=1, reason="x"), agent("undo"), agent("undo")])
    assert state["groups"]["g1"]["items"] == [1, 2, 3]
    assert state["kept"] == {} and 5 in state["undecided"]
    with pytest.raises(LogError, match="line 1: nothing to undo"):
        replay(NS, [agent("undo")])


@pytest.mark.parametrize("entry, message", [
    (agent("shuffle"), "unknown op 'shuffle'"),
    ({"who": "robot", "op": "keep", "item": 6}, "who must be proposal, agent or owner"),
    (agent("keep", item=99), "no item 99"),
    (agent("move", item=6, group="g9"), "no group 'g9'"),
    (agent("create", group="g1", name="again", items=[6]), "group 'g1' already exists"),
    (agent("create", group="g3", name="", items=[6]), "name is empty"),
    (agent("create", group="g3", name="x", items=[]), "items is empty"),
    (agent("create", group="g3", name="x", items=[6, 6]), "items repeats"),
    (agent("create", group="g3", name="x", items=[1]), "item 1 is already in group 'g1'"),
    (agent("drop", item=6), "reason is empty"),
    (agent("split", group="g1", items=[1, 2, 3], new="g3", name="x"), "would leave 'g1' empty"),
    (agent("split", group="g1", items=[4], new="g3", name="x"), "item 4 is not in group 'g1'"),
    (agent("merge", into="g1", groups=["g1"]), "cannot merge 'g1' into itself"),
    (owner("confirm", item=6), "item 6 is not kept"),
    (owner("confirm", group="g1", item=5), "takes one of: group, item, theme"),
])
def test_a_line_that_makes_no_sense_stops_the_replay(entry, message):
    with pytest.raises(LogError, match=f"line 4: .*{message}"):
        replay(NS, BASE + [entry])


def test_account_catches_an_item_that_is_lost_or_placed_twice():
    state = replay(NS, BASE)
    state["undecided"].discard(6)
    with pytest.raises(LogError, match=r"not accounted for: \[6\]"):
        account(NS, state)
    state = replay(NS, BASE)
    state["kept"][1] = {"confirmed": False}
    with pytest.raises(LogError, match=r"in more than one place: \[1\]"):
        account(NS, state)
    with pytest.raises(LogError, match=r"not in the document: \[6\]"):
        account(NS[:5], replay(NS, BASE))
    with pytest.raises(LogError, match=r"item numbers repeat: \[2\]"):
        account([1, 2, 2], replay([1, 2], []))


def test_break_replaces_an_item_with_its_parts():
    state = replay(NS, BASE + [owner("break", item=2, parts=["weed the beds", "order seeds"])])
    assert state["groups"]["g1"]["items"] == [1, 3]
    assert state["broken"] == {2: ["2.1", "2.2"]}
    assert state["parts"] == {"2.1": "weed the beds", "2.2": "order seeds"}
    assert state["undecided"] == {6, "2.1", "2.2"}
    counts = account(NS, state)
    assert (counts["items"], counts["broken"], counts["parts"]) == (6, 1, 2)
    assert counts["in_groups"] + counts["kept"] + counts["dropped"] + counts["undecided"] == 6 - 1 + 2


def test_parts_are_items_like_any_other():
    state = replay(NS, BASE + [
        owner("break", item=6, parts=["call the bank", "file the form", "buy stamps"]),
        agent("move", item="6.2", group="g2"),
        agent("move", item="6.1", group="g1"),
        agent("drop", item="6.3", reason="done already"),
        owner("break", item="6.1", parts=["find the number", "call"]),
    ])
    assert state["groups"]["g1"]["items"] == [1, 2, 3]
    assert state["groups"]["g2"]["items"] == [4, "6.2"]
    assert state["undecided"] == {"6.1.1", "6.1.2"}
    assert account(NS, state)["broken"] == 2


def test_break_unconfirms_the_group_it_takes_from_and_undo_puts_the_item_back():
    log = BASE + [owner("confirm", group="g1"), owner("break", item=1, parts=["dig", "plant"])]
    assert replay(NS, log)["groups"]["g1"]["confirmed"] is False
    state = replay(NS, log + [owner("undo")])
    assert state["groups"]["g1"]["items"] == [1, 2, 3]
    assert state["groups"]["g1"]["confirmed"] is True
    assert state["broken"] == {} and state["parts"] == {}


@pytest.mark.parametrize("entry, message", [
    (agent("break", item=6, parts=["a", "b"]), "only the owner breaks"),
    (owner("break", item=6, parts=["only one"]), "at least two"),
    (owner("break", item=6, parts=["a", " "]), "a part is empty"),
    (owner("break", item=9, parts=["a", "b"]), "no item 9"),
])
def test_a_break_that_makes_no_sense_is_refused(entry, message):
    with pytest.raises(LogError, match=f"line 4: break: .*{message}"):
        replay(NS, BASE + [entry])


def test_a_broken_item_can_no_longer_be_placed():
    with pytest.raises(LogError, match="line 5: keep: no item 6"):
        replay(NS, BASE + [owner("break", item=6, parts=["a", "b"]), agent("keep", item=6)])


def test_account_catches_a_lost_part():
    state = replay(NS, BASE + [owner("break", item=6, parts=["a", "b"])])
    state["undecided"].discard("6.2")
    with pytest.raises(LogError, match=r"not accounted for: \['6.2'\]"):
        account(NS, state)


THEMED = BASE + [agent("theme", theme="t1", name="outdoors", groups=["g1"], items=[6]),
                 agent("theme", theme="t2", name="desk", groups=["g2"], items=[5])]


def test_a_theme_holds_groups_and_items_that_stand_alone():
    state = replay(NS, THEMED)
    assert state["themes"]["t1"] == {"name": "outdoors", "groups": ["g1"], "items": [6], "later": False, "confirmed": False}
    counts = account(NS, state)
    assert (counts["themes"], counts["themes_confirmed"], counts["in_no_theme"]) == (2, 0, 0)
    assert account(NS, replay(NS, BASE))["in_no_theme"] == 4  # g1, g2, kept 5, undecided 6


def test_assign_fold_and_rename_a_theme():
    state = replay(NS, THEMED + [
        agent("assign", item=6, theme="t2"),
        agent("assign", item=5, theme=None),
        agent("rename", theme="t2", name="paper"),
    ])
    assert state["themes"]["t1"]["items"] == [] and state["themes"]["t2"]["items"] == [6]
    assert state["themes"]["t2"]["name"] == "paper"
    assert account(NS, state)["in_no_theme"] == 1
    state = replay(NS, THEMED + [agent("fold", into="t1", themes=["t2"])])
    assert state["themes"] == {"t1": {"name": "outdoors", "groups": ["g1", "g2"], "items": [5, 6], "later": False, "confirmed": False}}


def test_an_item_leaves_its_theme_when_it_stops_standing_alone():
    for edit in (agent("move", item=6, group="g2"), agent("drop", item=6, reason="x"),
                 owner("break", item=6, parts=["a", "b"])):
        state = replay(NS, THEMED + [edit])
        assert state["themes"]["t1"]["items"] == []
        account(NS, state)
    for edit in (agent("keep", item=6), agent("unassign", item=5)):
        state = replay(NS, THEMED + [edit])
        assert (state["themes"]["t1"]["items"], state["themes"]["t2"]["items"]) == ([6], [5])
        account(NS, state)


def test_groups_carry_their_theme_through_split_and_lose_it_when_they_go():
    state = replay(NS, THEMED + [agent("split", group="g1", items=[1], new="g3", name="shed")])
    assert state["themes"]["t1"]["groups"] == ["g1", "g3"]
    state = replay(NS, THEMED + [agent("merge", into="g1", groups=["g2"])])
    assert state["themes"]["t1"]["groups"] == ["g1"] and state["themes"]["t2"]["groups"] == []
    state = replay(NS, THEMED + [agent("assign", item=5, theme="t1"), agent("keep", item=4)])
    assert "t2" not in state["themes"]  # g2 emptied, and with it the theme
    account(NS, state)


@pytest.mark.parametrize("edit", [
    agent("rename", theme="t1", name="yard"),
    agent("assign", item=5, theme="t1"),
    agent("assign", group="g1", theme="t2"),
    agent("fold", into="t1", themes=["t2"]),
    agent("drop", item=6, reason="x"),
    agent("split", group="g1", items=[1], new="g3", name="shed"),
])
def test_changing_a_confirmed_theme_unconfirms_it(edit):
    confirmed = THEMED + [owner("confirm", theme="t1")]
    assert replay(NS, confirmed)["themes"]["t1"]["confirmed"] is True
    assert replay(NS, confirmed + [edit])["themes"]["t1"]["confirmed"] is False
    # Work inside a member group is not a change to the theme.
    assert replay(NS, confirmed + [agent("draft", group="g1", text="x")])["themes"]["t1"]["confirmed"] is True


@pytest.mark.parametrize("entry, message", [
    (agent("confirm", theme="t1"), "only the owner confirms"),
    (agent("theme", theme="t1", name="x", items=[5]), "theme 't1' already exists"),
    (agent("theme", theme="t3", name="x"), "groups and items are both empty"),
    (agent("theme", theme="t3", name="x", items=[6]), "6 is already in theme 't1'"),
    (agent("theme", theme="t3", name="x", groups=["g9"]), "no group 'g9'"),
    (agent("theme", theme="t3", name="x", items=[1]), "item 1 is in group 'g1'; a theme takes the group"),
    (agent("assign", item=1, theme="t1"), "item 1 is in group 'g1'"),
    (agent("assign", item=6, theme="t9"), "no theme 't9'"),
    (agent("assign", item=6, group="g1", theme="t1"), "takes one of: group, item"),
    (agent("fold", into="t1", themes=["t1"]), "cannot fold 't1' into itself"),
    (agent("rename", name="x"), "takes one of: group, theme"),
])
def test_a_theme_line_that_makes_no_sense_is_refused(entry, message):
    with pytest.raises(LogError, match=f"line 6: .*{message}"):
        replay(NS, THEMED + [entry])


def test_account_catches_a_theme_holding_what_it_cannot():
    state = replay(NS, THEMED)
    state["themes"]["t2"]["items"].append(6)
    with pytest.raises(LogError, match=r"members are in more than one theme: \[6\]"):
        account(NS, state)
    state = replay(NS, THEMED)
    state["themes"]["t1"]["items"].append(1)
    with pytest.raises(LogError, match=r"grouped, dropped, broken or unknown: \['t1'\]"):
        account(NS, state)


def test_append_writes_one_stamped_line_and_refuses_a_bad_one(tmp_path):
    (tmp_path / "items.jsonl").write_text("".join(json.dumps({"n": n, "text": f"job {n}"}) + "\n" for n in NS))
    for entry in BASE:
        append(tmp_path, entry)
    log = tmp_path / "work" / "log.jsonl"
    before = log.read_text()
    with pytest.raises(LogError, match="line 4: .*no item 99"):
        append(tmp_path, agent("keep", item=99))
    assert log.read_text() == before
    entries = read_log(log)
    assert [e["op"] for e in entries] == ["create", "create", "keep"]
    assert all(e["when"].endswith("+00:00") for e in entries)
    state, counts = load(tmp_path)
    assert counts["undecided"] == 1 and state["groups"]["g2"]["items"] == [4]


def test_a_broken_log_line_is_named(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(BASE[0]) + "\n{not json\n")
    with pytest.raises(LogError, match="line 2: not JSON"):
        read_log(log)


def test_later_marks_a_group_or_a_kept_item_and_keeps_an_undecided_one():
    state = replay(NS, BASE + [
        owner("confirm", group="g1"),
        owner("later", group="g1", on=True),
        owner("later", item=6, on=True),
        owner("later", item=5, on=True),
        owner("later", item=5, on=False),
    ])
    assert state["groups"]["g1"]["later"] is True and state["groups"]["g1"]["confirmed"] is True
    assert state["kept"] == {5: {"confirmed": False, "later": False}, 6: {"confirmed": False, "later": True}}
    counts = account(NS, state)
    assert (counts["later"], counts["kept"], counts["undecided"]) == (2, 2, 0)


def test_a_later_mark_follows_a_split_and_goes_when_the_item_is_no_longer_kept():
    state = replay(NS, BASE + [agent("later", group="g1", on=True), agent("split", group="g1", items=[1], new="g3", name="shed")])
    assert state["groups"]["g3"]["later"] is True
    state = replay(NS, BASE + [owner("later", item=5, on=True), owner("unassign", item=5), owner("keep", item=5)])
    assert state["kept"][5]["later"] is False


def test_later_on_a_theme_marks_all_of_it_and_keeps_its_undecided_items():
    marked = THEMED + [owner("confirm", theme="t1"), owner("later", theme="t1", on=True)]
    state = replay(NS, marked)
    assert state["themes"]["t1"]["later"] is True and state["themes"]["t1"]["confirmed"] is True
    assert state["kept"][6] == {"confirmed": False, "later": False} and state["groups"]["g1"]["later"] is False
    counts = account(NS, state)
    assert (counts["later"], counts["kept"], counts["undecided"]) == (2, 2, 0)  # g1 and item 6
    assert account(NS, replay(NS, marked + [owner("assign", item=6, theme="t2")]))["later"] == 1
    state = replay(NS, marked + [owner("later", theme="t1", on=False)])
    assert account(NS, state)["later"] == 0 and 6 in state["kept"]
    assert 6 in replay(NS, marked + [owner("undo")])["undecided"]


@pytest.mark.parametrize("entry, message", [
    (owner("later", theme="t9", on=True), "no theme 't9'"),
    (owner("later", item=1, on=True), "item 1 is in group 'g1'"),
    (owner("later", item=6, on=False), "item 6 is not kept"),
    (owner("later", group="g9", on=True), "no group 'g9'"),
    (owner("later", item=5, on="yes"), "on must be true or false"),
    (owner("later", item=5, group="g1", on=True), "takes one of"),
])
def test_later_refuses_what_it_cannot_mark(entry, message):
    with pytest.raises(LogError, match=message):
        replay(NS, BASE + [entry])
