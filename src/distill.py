"""The agent's commands for distilling one document. Each prints a short, bounded JSON answer.

    python -m src.distill status  todo-001
    python -m src.distill propose todo-001
    python -m src.distill groups  todo-001 [--unreviewed] [--limit N] [--offset N]
    python -m src.distill themes  todo-001 [--limit N] [--offset N]
    python -m src.distill show    todo-001 g12        (or a theme: t3, an item: 412, a part: 412.1)
    python -m src.distill suggest todo-001            (themes for what is in no theme)
    python -m src.distill break   todo-001 412 --who owner "first todo" "second todo"
    python -m src.distill export  todo-001 [--draft]

and the edits, each one line appended to the log, signed --who (default agent):

    create NAME ITEM...        rename GROUP|THEME NAME     merge INTO GROUP...
    split GROUP NAME ITEM...   move ITEM GROUP             keep ITEM
    drop ITEM|THEME REASON          unassign ITEM               draft GROUP|ITEM TEXT
    flag GROUP NOTE            theme NAME MEMBER...        assign MEMBER THEME|none
    fold INTO THEME...         undo

A MEMBER is a group id or an item. New groups and themes get the next free id.
There is no confirm here: only the owner confirms, in the UI.

`propose` needs the vectors from `python -m src.embed <doc>`. It writes
<doc>/work/proposal.json (both levels, and the settings used) and starts the log
with one `create` line per same-thing group and one `theme` line per theme,
signed "proposal". From then on groups and themes are read from the log.

`break` is the owner's: it splits an item that holds several todos into one
item per text (src/state.py refuses it from anyone else). `show` on an unbroken
item gives its sentence-by-sentence split as a starting point. Parts are
embedded the first time a command needs them, into <doc>/work/part_vectors.npz.

Output carries item text, which is private — see data/DATA.md.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from src import grouping, state
from src.embed import embed_items, fastembed_fn, read_items

ROOT = Path("data/raw/private/todo")
TEXT_CHARS = 160
NEIGHBOURS = 5
SUGGESTIONS = 3
# Looser than the theme cut: what is in no theme is what did not cluster at that cut.
NEW_THEME_CUT = 0.75


class DistillError(Exception):
    pass


def oldest_first(ns) -> list:
    # The top of the list is the oldest entry (the owner, SPEC_phase1_distill §9, question 2).
    return sorted(ns, key=state.order)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def _item_id(arg: str):
    if re.fullmatch(r"\d+", arg):
        return int(arg)
    return arg if re.fullmatch(r"\d+(\.\d+)+", arg) else None


def _clip(text: str) -> str:
    return text if len(text) <= TEXT_CHARS else text[: TEXT_CHARS - 1] + "…"


def _vectors(doc: Path, items: list[dict]) -> np.ndarray:
    path = doc / "work" / "vectors.npy"
    if not path.exists():
        raise DistillError(f"no vectors for this document; run: python -m src.embed {doc}")
    vectors = np.load(path)
    if len(vectors) != len(items):
        raise DistillError(f"{len(vectors)} vectors for {len(items)} items; run: python -m src.embed {doc}")
    return vectors


def _part_vectors(doc: Path, texts: list[str], dimensions: int) -> np.ndarray:
    """One row per part text, embedding the ones not yet in the cache. Keyed by text: undo frees a part id for other text."""
    work = doc / "work"
    cached = {}
    if (work / "part_vectors.npz").exists():
        with np.load(work / "part_vectors.npz") as f:
            cached = dict(zip(f["texts"].tolist(), f["vectors"]))
    missing = [t for t in dict.fromkeys(texts) if t not in cached]
    if missing:
        summary = work / "embed_summary.json"
        if not summary.exists():
            raise DistillError(f"no {summary}, so the model the items were embedded with is unknown; run: python -m src.embed {doc}")
        new = embed_items([{"n": t, "text": t} for t in missing], fastembed_fn(json.loads(summary.read_text())["model"]))
        if new.shape[1] != dimensions:
            raise DistillError(f"parts embed to {new.shape[1]} dimensions, the items to {dimensions}; run: python -m src.embed {doc}")
        cached.update(zip(missing, new))
        np.savez(work / "part_vectors.npz", texts=np.array(list(cached)), vectors=np.array(list(cached.values())))
    return np.array([cached[t] for t in texts])


_distance_cache: tuple = (None, None)


def _distance(doc: Path, originals: list[dict], parts: dict) -> np.ndarray:
    """Distances between every two items, the originals first and then the parts. Read-only.

    The review server asks for the same matrix on every click, so the latest one is kept
    until the vectors, an item's text or the parts change.
    """
    global _distance_cache
    vectors = _vectors(doc, originals)
    texts = [it["text"] for it in originals] + list(parts.values())
    key = (str(doc), (doc / "work" / "vectors.npy").stat().st_mtime_ns, tuple(texts))
    if _distance_cache[0] != key:
        if parts:
            vectors = np.vstack([vectors, _part_vectors(doc, list(parts.values()), vectors.shape[1])])
        matrix = grouping.combined_distance(vectors, texts)
        matrix.flags.writeable = False
        _distance_cache = (key, matrix)
    return _distance_cache[1]


def _where(st: dict) -> dict:
    where = {n: gid for gid, g in st["groups"].items() for n in g["items"]}
    where.update({n: "kept" for n in st["kept"]})
    where.update({n: "dropped" for n in st["dropped"]})
    where.update({n: "undecided" for n in st["undecided"]})
    where.update({n: "broken" for n in st["broken"]})
    return where


def _page(rows: list, args) -> tuple[dict, list]:
    shown = rows[args.offset : args.offset + args.limit]
    return {"total": len(rows), "offset": args.offset, "shown": len(shown)}, shown


def status(doc: Path, args) -> dict:
    counts = state.load(doc)[1]
    counts["proposed"] = (doc / "work" / "proposal.json").exists()
    return counts


def propose(doc: Path, args) -> dict:
    work = doc / "work"
    for name in ("proposal.json", "log.jsonl"):
        if (work / name).exists() and (work / name).stat().st_size:
            raise DistillError(f"{work / name} exists; a new proposal would orphan the decisions made on the old one. Move it away first.")
    items = read_items(doc / "items.jsonl")
    distance = grouping.combined_distance(_vectors(doc, items), [it["text"] for it in items])
    same, theme = grouping.two_level(distance, args.same_cut, args.theme_cut)
    ns = [it["n"] for it in items]
    groups = [
        {"id": f"g{k}", "items": [ns[i] for i in rows], "named_after": ns[grouping.medoid(distance, rows)]}
        for k, rows in enumerate(grouping.members(same), 1)
    ]
    themes = [
        {"id": f"t{k}", "items": [ns[i] for i in rows], "named_after": ns[grouping.medoid(distance, rows)]}
        for k, rows in enumerate(grouping.members(theme), 1)
    ]
    counts = {
        "items": len(items),
        "groups": len(groups),
        "items_in_groups": sum(len(g["items"]) for g in groups),
        "largest_group": max((len(g["items"]) for g in groups), default=0),
        "themes": len(themes),
        "items_in_themes": sum(len(t["items"]) for t in themes),
        "largest_theme": max((len(t["items"]) for t in themes), default=0),
    }
    counts["items_in_no_theme"] = counts["items"] - counts["items_in_themes"]
    settings = {"same_cut": args.same_cut, "theme_cut": args.theme_cut, "linkage": "average",
                "signals": "embedding cosine above the document median, TF-IDF 1-2-grams"}
    work.mkdir(exist_ok=True)
    (work / "proposal.json").write_text(
        json.dumps({"settings": settings, "counts": counts, "groups": groups, "themes": themes}, indent=1) + "\n")
    text = {it["n"]: it["text"] for it in items}
    for g in groups:
        state.append(doc, {"who": "proposal", "op": "create", "group": g["id"], "name": text[g["named_after"]], "items": g["items"]})
    group_of = {n: g["id"] for g in groups for n in g["items"]}
    for t in themes:
        # One tree cut twice, so a same-thing group never straddles two themes.
        state.append(doc, {
            "who": "proposal", "op": "theme", "theme": t["id"], "name": text[t["named_after"]],
            "groups": sorted({group_of[n] for n in t["items"] if n in group_of}),
            "items": [n for n in t["items"] if n not in group_of],
        })
    return counts


def groups(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    text = {**{it["n"]: it["text"] for it in read_items(doc / "items.jsonl")}, **st["parts"]}
    touched = set()
    for e in state.read_log(doc / "work" / "log.jsonl"):
        if e.get("who") != "proposal":
            touched.update([e.get("group"), e.get("into"), e.get("new"), *(e.get("groups") or [])])
    rows = []
    for gid, g in st["groups"].items():
        if args.unreviewed and gid in touched:
            continue
        ordered = oldest_first(g["items"])
        rows.append({
            "group": gid, "name": _clip(g["name"]), "size": len(ordered), "oldest": ordered[0],
            "span": [ordered[0], ordered[-1]], "draft": g["draft"], "flag": g["flag"],
            "confirmed": g["confirmed"], "sample": [_clip(text[n]) for n in ordered[:3]],
        })
    rows.sort(key=lambda r: state.order(r["oldest"]))
    page, shown = _page(rows, args)
    return {**page, "groups": shown}


def _theme_items(st: dict, t: dict) -> list:
    return t["items"] + [n for gid in t["groups"] for n in st["groups"][gid]["items"]]


def themes(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    where = _where(st)
    text = {**{it["n"]: it["text"] for it in read_items(doc / "items.jsonl")}, **st["parts"]}
    rows = []
    for tid, t in st["themes"].items():
        ordered = oldest_first(_theme_items(st, t))
        rows.append({
            "theme": tid, "name": _clip(t["name"]), "size": len(ordered), "groups": len(t["groups"]),
            "oldest": ordered[0], "span": [ordered[0], ordered[-1]],
            "undecided": sum(where[n] == "undecided" for n in ordered), "confirmed": t["confirmed"],
            "sample": [_clip(text[n]) for n in ordered[:3]],
        })
    rows.sort(key=lambda r: -r["size"])
    page, shown = _page(rows, args)
    return {**page, "themes": shown}


def show(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    originals = read_items(doc / "items.jsonl")
    items = originals + [{"n": pid, "text": text} for pid, text in st["parts"].items()]
    by_n = {it["n"]: it for it in items}
    n = _item_id(args.group)
    if args.group in st["groups"]:
        g = st["groups"][args.group]
        head = {"group": args.group, "name": g["name"], "draft": g["draft"], "flag": g["flag"], "confirmed": g["confirmed"]}
        inside = set(g["items"])
    elif n in by_n:
        head = {"item": n}
        if n in st["broken"]:
            head["parts"] = st["broken"][n]
        elif len(sentences(by_n[n]["text"])) > 1:
            head["split"] = sentences(by_n[n]["text"])
        inside = {n}
    elif args.group in st["themes"]:
        t = st["themes"][args.group]
        head = {"theme": args.group, "name": t["name"], "groups": t["groups"], "confirmed": t["confirmed"]}
        inside = set(_theme_items(st, t))
    else:
        raise DistillError(f"no group, theme or item {args.group!r}")
    where = _where(st)
    theme_of = {n: tid for tid, t in st["themes"].items() for n in _theme_items(st, t)}
    row = {it["n"]: i for i, it in enumerate(items)}
    distance = _distance(doc, originals, st["parts"])
    inside_rows = [row[n] for n in inside]
    nearest = distance[inside_rows].min(axis=0)
    # A broken item is no longer an item; its parts stand in for it as neighbours.
    nearest[inside_rows + [row[n] for n in st["broken"]]] = np.inf
    ordered = oldest_first(inside)

    def line(n) -> dict:
        return {"n": n, "text": _clip(by_n[n]["text"]), "detail": by_n[n].get("detail"),
                "where": where[n], "theme": theme_of.get(n)}

    return {
        **head, "size": len(ordered), "shown": min(len(ordered), args.limit),
        "items": [line(n) for n in ordered[: args.limit]],
        "nearest_outside": [
            {**line(items[i]["n"]), "distance": round(float(nearest[i]), 3)}
            for i in np.argsort(nearest)[:NEIGHBOURS] if np.isfinite(nearest[i])
        ],
    }


def suggest(doc: Path, args) -> dict:
    """For each group and lone item in no theme: the themes of the nearest items that have one, nearest first.

    Only a hint for the owner; nothing is logged. A neighbour farther than the
    theme cut suggests nothing, so a member can be missing from the answer.
    "new" is the themes those members could form among themselves: the clusters of
    two or more at NEW_THEME_CUT, each named after its most central member.
    """
    st, _ = state.load(doc)
    originals = read_items(doc / "items.jsonl")
    row = {n: i for i, n in enumerate([it["n"] for it in originals] + list(st["parts"]))}
    theme_of_row = {row[n]: tid for tid, t in st["themes"].items() for n in _theme_items(st, t)}
    themed_items = {n for t in st["themes"].values() for n in t["items"]}
    themed_groups = {gid for t in st["themes"].values() for gid in t["groups"]}
    loose = {"items": {n: [n] for n in [*st["undecided"], *st["kept"]] if n not in themed_items},
             "groups": {gid: g["items"] for gid, g in st["groups"].items() if gid not in themed_groups}}
    out: dict = {"items": {}, "groups": {}, "new": []}
    if not (loose["items"] or loose["groups"]):
        return out
    distance = _distance(doc, originals, st["parts"])
    themed = np.array(sorted(theme_of_row))
    for kind, members in loose.items():
        for member, ns in members.items() if theme_of_row else ():
            nearest = distance[[row[n] for n in ns]][:, themed].min(axis=0)
            found: list = []
            for i in np.argsort(nearest):
                if nearest[i] > grouping.THEME_CUT or len(found) == SUGGESTIONS:
                    break
                if theme_of_row[themed[i]] not in found:
                    found.append(theme_of_row[themed[i]])
            if found:
                out[kind][str(member)] = found
    flat = [(kind, member, [row[n] for n in ns]) for kind, members in loose.items() for member, ns in members.items()]
    between = np.zeros((len(flat), len(flat)))
    for i, (_, _, a) in enumerate(flat):
        for j in range(i + 1, len(flat)):
            between[i, j] = between[j, i] = distance[np.ix_(a, flat[j][2])].mean()
    for rows in grouping.members(grouping.two_level(between, NEW_THEME_CUT, NEW_THEME_CUT)[1]):
        central = flat[grouping.medoid(between, rows)]
        out["new"].append({"items": [flat[i][1] for i in rows if flat[i][0] == "items"],
                           "groups": [flat[i][1] for i in rows if flat[i][0] == "groups"],
                           "named_after": central[1]})
    return out


def break_item(doc: Path, args) -> dict:
    n = _item_id(args.item)
    state.append(doc, {"who": args.who, "op": "break", "item": n, "parts": args.parts})
    st, _ = state.load(doc)
    return {"item": n, "parts": [{"n": pid, "text": _clip(st["parts"][pid])} for pid in st["broken"][n]]}


def _item(arg: str):
    n = _item_id(arg)
    if n is None:
        raise DistillError(f"not an item: {arg!r}")
    return n


def _member(arg: str) -> dict:
    n = _item_id(arg)
    return {"group": arg} if n is None else {"item": n}


def _next_id(doc: Path, prefix: str) -> str:
    # From the log, not the state: an id that was merged away or undone is not reused.
    used = [e.get(k) for e in state.read_log(doc / "work" / "log.jsonl") for k in ("group", "new", "theme")]
    return f"{prefix}{max((int(u[len(prefix):]) for u in used if isinstance(u, str) and re.fullmatch(prefix + r'\d+', u)), default=0) + 1}"


def _new_theme(doc: Path, a) -> dict:
    members = [_member(m) for m in a.members]
    return {"theme": _next_id(doc, "t"), "name": a.name,
            "groups": [m["group"] for m in members if "group" in m], "items": [m["item"] for m in members if "item" in m]}


def _later(doc: Path, a) -> dict:
    if a.on not in ("on", "off"):
        raise DistillError(f"later takes on or off, not {a.on!r}")
    target = {"theme": a.member} if a.member in state.load(doc)[0]["themes"] else _member(a.member)
    return {**target, "on": a.on == "on"}


# Each edit: its arguments (a trailing + takes one or more), and the log fields they become.
EDITS = {
    "create": ("name items+", lambda doc, a: {"group": _next_id(doc, "g"), "name": a.name, "items": [_item(x) for x in a.items]}),
    "rename": ("target name", lambda doc, a: {"theme" if a.target in state.load(doc)[0]["themes"] else "group": a.target, "name": a.name}),
    "merge": ("into groups+", lambda doc, a: {"into": a.into, "groups": a.groups}),
    "split": ("group name items+", lambda doc, a: {"group": a.group, "items": [_item(x) for x in a.items], "new": _next_id(doc, "g"), "name": a.name}),
    "move": ("item group", lambda doc, a: {"item": _item(a.item), "group": a.group}),
    "keep": ("item", lambda doc, a: {"item": _item(a.item)}),
    "drop": ("item reason", lambda doc, a: {**({"theme": a.item} if a.item in state.load(doc)[0]["themes"] else {"item": _item(a.item)}), "reason": a.reason}),
    "unassign": ("item", lambda doc, a: {"item": _item(a.item)}),
    "draft": ("member text", lambda doc, a: {**_member(a.member), "text": a.text}),
    "flag": ("group note", lambda doc, a: {"group": a.group, "note": a.note}),
    "later": ("member on", _later),
    "theme": ("name members+", _new_theme),
    "assign": ("member theme", lambda doc, a: {**_member(a.member), "theme": None if a.theme == "none" else a.theme}),
    "fold": ("into themes+", lambda doc, a: {"into": a.into, "themes": a.themes}),
    "undo": ("", lambda doc, a: {}),
}


def edit(doc: Path, args) -> dict:
    return {"logged": state.append(doc, {"who": args.who, "op": args.command, **EDITS[args.command][1](doc, args)})}


def export(doc: Path, args) -> dict:
    """Write <doc>/work/distilled.md from the log: themes as sections, then what each line replaces."""
    st, counts = state.load(doc)
    text = {**{it["n"]: it["text"] for it in read_items(doc / "items.jsonl")}, **st["parts"]}
    section_of = {("g", gid): tid for tid, t in st["themes"].items() for gid in t["groups"]}
    section_of.update({("i", n): tid for tid, t in st["themes"].items() for n in t["items"]})
    sections: dict = {}
    later: list = []

    def place(key: tuple, marked: bool, ns: list, line: str) -> None:
        tid = section_of.get(key)
        if marked or (tid is not None and st["themes"][tid]["later"]):
            later.append((ns, line + (f" ({st['themes'][tid]['name']})" if tid is not None else "")))
        else:
            sections.setdefault(tid, []).append((ns, line))

    for gid, g in st["groups"].items():
        if g["confirmed"] or args.draft:
            line = (g["draft"] or g["name"]) + ("" if g["confirmed"] else " (not confirmed)")
            place(("g", gid), g["later"], oldest_first(g["items"]), line)
    for n, k in st["kept"].items():
        place(("i", n), k["later"], [n], k["draft"] or text[n])
    # Largest section first, items in no theme last; within a section, oldest first.
    order = sorted(sections, key=lambda tid: (tid is None, -len(sections[tid]), str(tid)))
    out, appendix, k = [f"# {doc.name}, distilled", ""], [], 0
    titled = [(st["themes"][tid]["name"] if tid is not None else "In no theme", sections[tid]) for tid in order]
    for title, rows in titled + ([("Later", later)] if later else []):
        out += [f"## {title}", ""]
        for ns, line in sorted(rows, key=lambda row: state.order(row[0][0])):
            k += 1
            out.append(f"- {line} [{k}]")
            appendix += [f"**[{k}]** {line}", ""] + [f"- {n}: {text[n]}" for n in ns] + [""]
        out.append("")
    out += ["## What each line replaces", ""] + appendix
    out += ["## Dropped", ""] + [f"- {n}: {text[n]} — {st['dropped'][n]}" for n in oldest_first(st["dropped"])] + [""]
    left = {"undecided": counts["undecided"], "groups_not_confirmed": counts["groups"] - counts["groups_confirmed"]}
    out += ["## Still open", "", f"- {left['undecided']} items undecided",
            f"- {left['groups_not_confirmed']} groups not confirmed" + ("" if args.draft else " (left out; --draft includes them)"), ""]
    path = doc / "work" / "distilled.md"
    path.write_text("\n".join(out), encoding="utf-8")
    return {"wrote": str(path), "lines": k, "sections": len(order), "later": len(later), "dropped": counts["dropped"], **left}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="folder holding one folder per document")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, (spec, _) in EDITS.items():
        p = sub.add_parser(name)
        p.set_defaults(fn=edit)
        p.add_argument("id", help="document id, e.g. todo-001")
        for arg in spec.split():
            p.add_argument(arg.rstrip("+"), **({"nargs": "+"} if arg.endswith("+") else {}))
        p.add_argument("--who", default="agent", choices=("agent", "owner"))
    for fn in (status, propose, groups, themes, show, suggest, break_item, export):
        p = sub.add_parser(fn.__name__.removesuffix("_item"))
        p.set_defaults(fn=fn)
        p.add_argument("id", help="document id, e.g. todo-001")
        if fn is propose:
            p.add_argument("--same-cut", type=float, default=grouping.SAME_CUT)
            p.add_argument("--theme-cut", type=float, default=grouping.THEME_CUT)
        if fn is show:
            p.add_argument("group", help="a group id (g12), a theme id (t3), an item (412) or a part (412.1)")
            p.add_argument("--limit", type=int, default=50)
        if fn is break_item:
            p.add_argument("item", help="an item (412) or a part (412.1)")
            p.add_argument("parts", nargs="+", help="the text of each new item")
            p.add_argument("--who", required=True, help="owner; the log refuses a break from anyone else")
        if fn is export:
            p.add_argument("--draft", action="store_true", help="include groups the owner has not confirmed, marked as such")
        if fn in (groups, themes):
            p.add_argument("--limit", type=int, default=20)
            p.add_argument("--offset", type=int, default=0)
        if fn is groups:
            p.add_argument("--unreviewed", action="store_true", help="only groups no agent or owner decision has touched")
    args = ap.parse_args(argv)
    try:
        out = args.fn(args.root / args.id, args)
    except (DistillError, state.LogError, FileNotFoundError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
