"""A document's review state: the decision log, its replay, and the accounted-for check.

    python -m src.state data/raw/private/todo/todo-001

Prints the counts for <doc> as JSON. <doc>/work/log.jsonl holds one decision per
line and is only ever appended to; the state is that log replayed from the top
over the items in <doc>/items.jsonl. Both are private — see data/DATA.md.

A log line is {"who": "agent" | "owner", "when": ISO time, "op": ..., fields}:

    create    group, name, items   a new group of items that are in no group yet
    rename    group, name
    merge     into, groups         the items of `groups` join `into`
    split     group, items, new, name   some of a group's items become group `new`
    move      item, group          from wherever the item is
    keep      item                 stays in the new list on its own
    drop      item, reason
    unassign  item                 back to undecided
    draft     group, text          the group's line in the new list
    flag      group, note          marked for the owner
    confirm   group | item         owner only; an item must be kept
    undo                           ignore the latest line not yet undone

Changing a confirmed group in any way unconfirms it. A line that makes no sense
stops the replay with its line number; `append` checks a line before writing
it, so that should only happen to a log edited by hand.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


class LogError(ValueError):
    pass


def read_log(path: Path) -> list[dict]:
    entries = []
    if not path.exists():
        return entries
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise LogError(f"{path} line {i}: not JSON ({exc.msg})") from None
    return entries


def _text(entry: dict, key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LogError(f"{key} is empty")
    return value


def _apply(state: dict, known: set, e: dict) -> None:
    groups, kept, dropped, undecided = state["groups"], state["kept"], state["dropped"], state["undecided"]

    def group(key: str = "group") -> dict:
        if e.get(key) not in groups:
            raise LogError(f"no group {e.get(key)!r}")
        return groups[e[key]]

    def new_group(key: str) -> dict:
        gid = _text(e, key)
        if gid in groups:
            raise LogError(f"group {gid!r} already exists")
        name = _text(e, "name")
        groups[gid] = {"name": name, "items": [], "draft": None, "flag": None, "confirmed": False}
        return groups[gid]

    def item() -> int:
        if e.get("item") not in known:
            raise LogError(f"no item {e.get('item')!r}")
        return e["item"]

    def items() -> list:
        ns = e.get("items")
        if not ns:
            raise LogError("items is empty")
        if len(set(ns)) != len(ns):
            raise LogError("items repeats a number")
        for n in ns:
            if n not in known:
                raise LogError(f"no item {n!r}")
        return ns

    def home(n: int) -> str | None:
        return next((gid for gid, g in groups.items() if n in g["items"]), None)

    def take(n: int) -> None:
        undecided.discard(n)
        kept.pop(n, None)
        dropped.pop(n, None)
        gid = home(n)
        if gid is not None:
            groups[gid]["items"].remove(n)
            groups[gid]["confirmed"] = False
            if not groups[gid]["items"]:
                del groups[gid]

    def put(g: dict, ns: list) -> None:
        g["items"] = sorted(g["items"] + ns)
        g["confirmed"] = False

    if e.get("who") not in ("agent", "owner"):
        raise LogError("who must be agent or owner")
    op = e.get("op")
    if op == "create":
        ns = items()
        for n in ns:
            if home(n) is not None:
                raise LogError(f"item {n} is already in group {home(n)!r}")
        g = new_group("group")
        for n in ns:
            take(n)
        put(g, ns)
    elif op == "rename":
        g = group()
        g["name"], g["confirmed"] = _text(e, "name"), False
    elif op == "merge":
        into = group("into")
        for gid in e.get("groups") or [None]:
            if gid == e["into"]:
                raise LogError(f"cannot merge {gid!r} into itself")
            if gid not in groups:
                raise LogError(f"no group {gid!r}")
            put(into, groups.pop(gid)["items"])
    elif op == "split":
        g, ns = group(), items()
        for n in ns:
            if n not in g["items"]:
                raise LogError(f"item {n} is not in group {e['group']!r}")
        if len(ns) == len(g["items"]):
            raise LogError(f"would leave {e['group']!r} empty")
        new = new_group("new")
        for n in ns:
            take(n)
        put(new, ns)
    elif op == "move":
        n, g = item(), group()
        if n not in g["items"]:
            take(n)
            put(g, [n])
    elif op == "keep":
        n = item()
        if n not in kept:
            take(n)
            kept[n] = {"confirmed": False}
    elif op == "drop":
        n, reason = item(), _text(e, "reason")
        take(n)
        dropped[n] = reason
    elif op == "unassign":
        n = item()
        take(n)
        undecided.add(n)
    elif op == "draft":
        g = group()
        g["draft"], g["confirmed"] = _text(e, "text"), False
    elif op == "flag":
        group()["flag"] = _text(e, "note")
    elif op == "confirm":
        if e["who"] != "owner":
            raise LogError("only the owner confirms")
        if ("group" in e) == ("item" in e):
            raise LogError("confirm takes a group or an item, one of them")
        if "group" in e:
            g = group()
            g["confirmed"], g["flag"] = True, None
        else:
            n = item()
            if n not in kept:
                raise LogError(f"item {n} is not kept")
            kept[n]["confirmed"] = True
    else:
        raise LogError(f"unknown op {op!r}")


def replay(item_ns: list, entries: list[dict]) -> dict:
    """The state after every entry, in order. Line numbers in errors count from 1."""
    live: list[tuple[int, dict]] = []
    for i, e in enumerate(entries, 1):
        if e.get("op") == "undo":
            if not live:
                raise LogError(f"line {i}: nothing to undo")
            live.pop()
        else:
            live.append((i, e))
    known = set(item_ns)
    state = {"groups": {}, "kept": {}, "dropped": {}, "undecided": set(item_ns)}
    for i, e in live:
        try:
            _apply(state, known, e)
        except LogError as exc:
            raise LogError(f"line {i}: {e.get('op')}: {exc}") from None
    return state


def account(item_ns: list, state: dict) -> dict:
    """Counts, after checking every item is in exactly one place: a group, kept, dropped or undecided."""
    repeats = sorted(n for n, c in Counter(item_ns).items() if c > 1)
    if repeats:
        raise LogError(f"item numbers repeat: {repeats[:10]}")
    groups = state["groups"]
    in_groups = [n for g in groups.values() for n in g["items"]]
    placed = Counter(in_groups + list(state["kept"]) + list(state["dropped"]) + list(state["undecided"]))
    for problem, ns in (
        ("not accounted for", sorted(set(item_ns) - set(placed))),
        ("in more than one place", sorted(n for n, c in placed.items() if c > 1)),
        ("not in the document", sorted(set(placed) - set(item_ns))),
    ):
        if ns:
            raise LogError(f"{len(ns)} items {problem}: {ns[:10]}")
    return {
        "items": len(item_ns),
        "in_groups": len(in_groups),
        "kept": len(state["kept"]),
        "dropped": len(state["dropped"]),
        "undecided": len(state["undecided"]),
        "groups": len(groups),
        "groups_confirmed": sum(g["confirmed"] for g in groups.values()),
        "groups_flagged": sum(g["flag"] is not None for g in groups.values()),
        "kept_confirmed": sum(k["confirmed"] for k in state["kept"].values()),
    }


def item_numbers(doc: Path) -> list:
    with (doc / "items.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line)["n"] for line in fh if line.strip()]


def load(doc: Path) -> tuple[dict, dict]:
    ns = item_numbers(doc)
    state = replay(ns, read_log(doc / "work" / "log.jsonl"))
    return state, account(ns, state)


def append(doc: Path, entry: dict) -> dict:
    """Add one decision to the log, stamped with the time, unless the log would no longer replay."""
    ns = item_numbers(doc)
    path = doc / "work" / "log.jsonl"
    path.parent.mkdir(exist_ok=True)
    entry = {"who": entry.get("who"), "when": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with path.open("a+", encoding="utf-8") as fh:
        # Held across check and write, so the agent and the UI cannot both
        # append a line that was only valid before the other's.
        fcntl.flock(fh, fcntl.LOCK_EX)
        account(ns, replay(ns, read_log(path) + [entry]))
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("doc", type=Path, help="document folder holding items.jsonl")
    args = ap.parse_args(argv)
    print(json.dumps(load(args.doc)[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
