"""A document's review state: the decision log, its replay, and the accounted-for check.

    python -m src.state data/raw/private/todo/todo-001

Prints the counts for <doc> as JSON. <doc>/work/log.jsonl holds one decision per
line and is only ever appended to; the state is that log replayed from the top
over the items in <doc>/items.jsonl. Both are private — see data/DATA.md.

A log line is {"who": "proposal" | "agent" | "owner", "when": ISO time, "op": ...,
fields}; "proposal" is the grouping algorithm (src/distill.py propose):

    create    group, name, items   a new group of items that are in no group yet
    rename    group | theme, name
    merge     into, groups         the items of `groups` join `into`
    split     group, items, new, name   some of a group's items become group `new`
    move      item, group          from wherever the item is
    keep      item                 stays in the new list on its own
    drop      item, reason
    unassign  item                 back to undecided
    break     item, parts          owner only; the item becomes one new item per text
                                   in `parts`, numbered <item>.1, <item>.2, ..., all undecided
    draft     group | item, text   its line in the new list; an undecided item is kept by it
    flag      group, note          marked for the owner
    later     group | item | theme, on   on true: its line goes in the "Later" section at the bottom of
                                   the new list; an undecided item is kept by it. on false: unmarked.
                                   A theme: every line of the theme goes there, and its undecided
                                   items are kept
    theme     theme, name, groups, items   a new theme: a named section of the new list, holding
                                   groups and single items that are in no theme yet
    assign    group | item, theme  into that theme from whichever it was in; theme null: into none
    fold      into, themes         the members of `themes` join `into`
    confirm   group | item | theme owner only; an item must be kept
    undo                           ignore the latest line not yet undone

A broken item is no longer placed anywhere; its parts are items like any other
(a part can be broken again) and carry their text in the log, since items.jsonl
does not hold them. A theme holds whole groups, and items that stand alone
(undecided or kept): an item that joins a group, is dropped or is broken leaves
its theme, a group split off another starts in the same theme, and a group or
theme that loses its last member is gone. Changing a confirmed group in any way
unconfirms it, and so does changing a confirmed theme's name or members; a flag
or a later mark changes neither. A later mark stays with its group or kept item
(a group split off a marked group is marked too) and goes when the item stops
being kept. A later mark on a theme stays with the theme: what joins the theme
afterwards is later too (an undecided item that joins is not kept by that), what
leaves it is not, and a theme folded into another takes the other's mark. A line
that makes no sense
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


def order(n) -> tuple:
    """Sorts item numbers and part ids together: 7 < "7.1" < "7.2" < 8."""
    return tuple(int(x) for x in str(n).split("."))


def _apply(state: dict, known: set, e: dict) -> None:
    groups, kept, dropped, undecided = state["groups"], state["kept"], state["dropped"], state["undecided"]
    themes = state["themes"]

    def one_of(*keys: str) -> str:
        given = [k for k in keys if k in e]
        if len(given) != 1:
            raise LogError(f"takes one of: {', '.join(keys)}")
        return given[0]

    def theme(key: str = "theme") -> dict:
        if e.get(key) not in themes:
            raise LogError(f"no theme {e.get(key)!r}")
        return themes[e[key]]

    def themed(kind: str, member) -> str | None:
        return next((tid for tid, t in themes.items() if member in t[kind]), None)

    def leave(kind: str, member) -> None:
        tid = themed(kind, member)
        if tid is not None:
            themes[tid][kind].remove(member)
            themes[tid]["confirmed"] = False
            if not themes[tid]["groups"] and not themes[tid]["items"]:
                del themes[tid]

    def join(t: dict, kind: str, members: list) -> None:
        t[kind] = sorted(t[kind] + members, key=order if kind == "items" else None)
        t["confirmed"] = False

    def loose(n):
        if n not in known:
            raise LogError(f"no item {n!r}")
        if home(n) is not None:
            raise LogError(f"item {n} is in group {home(n)!r}; a theme takes the group")
        if n in dropped:
            raise LogError(f"item {n} is dropped")
        return n

    def group(key: str = "group") -> dict:
        if e.get(key) not in groups:
            raise LogError(f"no group {e.get(key)!r}")
        return groups[e[key]]

    def new_group(key: str) -> dict:
        gid = _text(e, key)
        if gid in groups:
            raise LogError(f"group {gid!r} already exists")
        name = _text(e, "name")
        groups[gid] = {"name": name, "items": [], "draft": None, "flag": None, "later": False, "confirmed": False}
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

    def take(n: int, themed: bool = False) -> None:
        undecided.discard(n)
        kept.pop(n, None)
        dropped.pop(n, None)
        if not themed:
            leave("items", n)
        gid = home(n)
        if gid is not None:
            groups[gid]["items"].remove(n)
            groups[gid]["confirmed"] = False
            if not groups[gid]["items"]:
                del groups[gid]
                leave("groups", gid)

    def put(g: dict, ns: list) -> None:
        g["items"] = sorted(g["items"] + ns, key=order)
        g["confirmed"] = False

    if e.get("who") not in ("proposal", "agent", "owner"):
        raise LogError("who must be proposal, agent or owner")
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
        target = group() if one_of("group", "theme") == "group" else theme()
        target["name"], target["confirmed"] = _text(e, "name"), False
    elif op == "merge":
        into = group("into")
        for gid in e.get("groups") or [None]:
            if gid == e["into"]:
                raise LogError(f"cannot merge {gid!r} into itself")
            if gid not in groups:
                raise LogError(f"no group {gid!r}")
            put(into, groups.pop(gid)["items"])
            leave("groups", gid)
    elif op == "split":
        g, ns = group(), items()
        for n in ns:
            if n not in g["items"]:
                raise LogError(f"item {n} is not in group {e['group']!r}")
        if len(ns) == len(g["items"]):
            raise LogError(f"would leave {e['group']!r} empty")
        new = new_group("new")
        new["later"] = g["later"]
        for n in ns:
            take(n)
        put(new, ns)
        if themed("groups", e["group"]) is not None:
            join(themes[themed("groups", e["group"])], "groups", [e["new"]])
    elif op == "move":
        n, g = item(), group()
        if n not in g["items"]:
            take(n)
            put(g, [n])
    elif op == "keep":
        n = item()
        if n not in kept:
            take(n, themed=True)
            kept[n] = {"draft": None, "confirmed": False, "later": False}
    elif op == "later":
        on = e.get("on")
        if not isinstance(on, bool):
            raise LogError("on must be true or false")
        kind = one_of("group", "item", "theme")
        if kind == "group":
            group()["later"] = on
        elif kind == "theme":
            t = theme()
            t["later"] = on
            for n in t["items"] if on else []:
                if n in undecided:
                    undecided.discard(n)
                    kept[n] = {"draft": None, "confirmed": False, "later": False}
        else:
            n = loose(e["item"])
            if n not in kept:
                if not on:
                    raise LogError(f"item {n} is not kept")
                take(n, themed=True)
                kept[n] = {"draft": None, "confirmed": False, "later": False}
            kept[n]["later"] = on
    elif op == "drop":
        n, reason = item(), _text(e, "reason")
        take(n)
        dropped[n] = reason
    elif op == "unassign":
        n = item()
        take(n, themed=True)
        undecided.add(n)
    elif op == "break":
        if e["who"] != "owner":
            raise LogError("only the owner breaks an item")
        n, texts = item(), e.get("parts")
        if not isinstance(texts, list) or len(texts) < 2:
            raise LogError("parts needs at least two texts")
        if not all(isinstance(t, str) and t.strip() for t in texts):
            raise LogError("a part is empty")
        take(n)
        known.discard(n)
        state["broken"][n] = [f"{n}.{k}" for k in range(1, len(texts) + 1)]
        for pid, t in zip(state["broken"][n], texts):
            state["parts"][pid] = t
            known.add(pid)
            undecided.add(pid)
    elif op == "draft":
        if one_of("group", "item") == "group":
            target = group()
        else:
            n = loose(e["item"])
            if n not in kept:
                take(n, themed=True)
                kept[n] = {"draft": None, "confirmed": False, "later": False}
            target = kept[n]
        target["draft"], target["confirmed"] = _text(e, "text"), False
    elif op == "flag":
        group()["flag"] = _text(e, "note")
    elif op == "theme":
        tid, name = _text(e, "theme"), _text(e, "name")
        if tid in themes:
            raise LogError(f"theme {tid!r} already exists")
        gids, ns = e.get("groups") or [], e.get("items") or []
        if not gids and not ns:
            raise LogError("groups and items are both empty")
        if len(set(gids)) != len(gids) or len(set(ns)) != len(ns):
            raise LogError("a member repeats")
        for kind, members in (("groups", gids), ("items", ns)):
            for m in members:
                if kind == "groups" and m not in groups:
                    raise LogError(f"no group {m!r}")
                if kind == "items":
                    loose(m)
                if themed(kind, m) is not None:
                    raise LogError(f"{m!r} is already in theme {themed(kind, m)!r}")
        themes[tid] = {"name": name, "groups": [], "items": [], "later": False, "confirmed": False}
        join(themes[tid], "groups", gids)
        join(themes[tid], "items", ns)
    elif op == "assign":
        kind = one_of("group", "item") + "s"
        if kind == "groups":
            group()
        member = e["group"] if kind == "groups" else loose(e["item"])
        tid = e.get("theme")
        if tid is not None:
            theme()
        if themed(kind, member) != tid:
            leave(kind, member)
            if tid is not None:
                join(themes[tid], kind, [member])
    elif op == "fold":
        into = theme("into")
        for tid in e.get("themes") or [None]:
            if tid == e["into"]:
                raise LogError(f"cannot fold {tid!r} into itself")
            if tid not in themes:
                raise LogError(f"no theme {tid!r}")
            gone = themes.pop(tid)
            join(into, "groups", gone["groups"])
            join(into, "items", gone["items"])
    elif op == "confirm":
        if e["who"] != "owner":
            raise LogError("only the owner confirms")
        kind = one_of("group", "item", "theme")
        if kind == "group":
            g = group()
            g["confirmed"], g["flag"] = True, None
        elif kind == "theme":
            theme()["confirmed"] = True
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
    state = {"groups": {}, "kept": {}, "dropped": {}, "undecided": set(item_ns), "broken": {}, "parts": {}, "themes": {}}
    for i, e in live:
        try:
            _apply(state, known, e)
        except LogError as exc:
            raise LogError(f"line {i}: {e.get('op')}: {exc}") from None
    return state


def account(item_ns: list, state: dict) -> dict:
    """Counts, after checking every item is in exactly one place: a group, kept, dropped or undecided.

    A broken item is in none of them; each of its parts must be in one. A theme's members must exist,
    stand where a theme can hold them, and be in no other theme.
    """
    repeats = sorted(n for n, c in Counter(item_ns).items() if c > 1)
    if repeats:
        raise LogError(f"item numbers repeat: {repeats[:10]}")
    groups = state["groups"]
    in_groups = [n for g in groups.values() for n in g["items"]]
    placed = Counter(in_groups + list(state["kept"]) + list(state["dropped"]) + list(state["undecided"]))
    broken, parts = state["broken"], state["parts"]
    expected = (set(item_ns) | set(parts)) - set(broken)
    for problem, ns in (
        ("not accounted for", expected - set(placed)),
        ("in more than one place", {n for n, c in placed.items() if c > 1}),
        ("not in the document", set(placed) - expected),
        ("broken without their parts", {n for n, pids in broken.items() if not set(pids) <= set(parts)}),
    ):
        ns = sorted(ns, key=order)
        if ns:
            raise LogError(f"{len(ns)} items {problem}: {ns[:10]}")
    themes = state["themes"]
    alone = set(state["kept"]) | set(state["undecided"])
    themed_groups = Counter(gid for t in themes.values() for gid in t["groups"])
    themed_items = Counter(n for t in themes.values() for n in t["items"])
    for problem, found in (
        ("themes are empty", [tid for tid, t in themes.items() if not t["groups"] and not t["items"]]),
        ("themes hold a group that does not exist", [tid for tid, t in themes.items() if not set(t["groups"]) <= set(groups)]),
        ("themes hold an item that is grouped, dropped, broken or unknown", [tid for tid, t in themes.items() if not set(t["items"]) <= alone]),
        ("members are in more than one theme", [m for counts in (themed_groups, themed_items) for m, c in counts.items() if c > 1]),
    ):
        if found:
            raise LogError(f"{len(found)} {problem}: {found[:10]}")
    return {
        "items": len(item_ns),
        "in_groups": len(in_groups),
        "kept": len(state["kept"]),
        "dropped": len(state["dropped"]),
        "undecided": len(state["undecided"]),
        "broken": len(broken),
        "parts": len(parts),
        "groups": len(groups),
        "groups_confirmed": sum(g["confirmed"] for g in groups.values()),
        "groups_flagged": sum(g["flag"] is not None for g in groups.values()),
        "kept_confirmed": sum(k["confirmed"] for k in state["kept"].values()),
        "later": len({("g", gid) for gid, g in groups.items() if g["later"]}
                     | {("i", n) for n, k in state["kept"].items() if k["later"]}
                     | {(kind[0], m) for t in themes.values() if t["later"] for kind in ("groups", "items")
                        for m in t[kind] if kind == "groups" or m in state["kept"]}),
        "themes": len(themes),
        "themes_confirmed": sum(t["confirmed"] for t in themes.values()),
        "in_no_theme": len(groups) - len(themed_groups) + len(alone) - len(themed_items),
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
