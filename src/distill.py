"""The agent's commands for distilling one document. Each prints a short, bounded JSON answer.

    python -m src.distill status  todo-001
    python -m src.distill propose todo-001
    python -m src.distill groups  todo-001 [--unreviewed] [--limit N] [--offset N]
    python -m src.distill themes  todo-001 [--limit N] [--offset N]
    python -m src.distill show    todo-001 g12        (or a theme: t3)

`propose` needs the vectors from `python -m src.embed <doc>`. It writes
<doc>/work/proposal.json (both levels, and the settings used) and starts the log
with one `create` line per same-thing group, signed "proposal". Themes are a
suggestion read from proposal.json; they are not review state yet.

Output carries item text, which is private — see data/DATA.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src import grouping, state
from src.embed import read_items

ROOT = Path("data/raw/private/todo")
TEXT_CHARS = 160
NEIGHBOURS = 5


class DistillError(Exception):
    pass


def oldest_first(ns) -> list:
    # Read for now as: farther down the list is older (SPEC_phase1_distill §9, question 2).
    return sorted(ns, reverse=True)


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


def _proposal(doc: Path) -> dict:
    path = doc / "work" / "proposal.json"
    if not path.exists():
        raise DistillError(f"no proposal for this document; run: python -m src.distill propose {doc.name}")
    return json.loads(path.read_text())


def _where(st: dict) -> dict:
    where = {n: gid for gid, g in st["groups"].items() for n in g["items"]}
    where.update({n: "kept" for n in st["kept"]})
    where.update({n: "dropped" for n in st["dropped"]})
    where.update({n: "undecided" for n in st["undecided"]})
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
    themes = [{"id": f"t{k}", "items": [ns[i] for i in rows]} for k, rows in enumerate(grouping.members(theme), 1)]
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
    return counts


def groups(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    text = {it["n"]: it["text"] for it in read_items(doc / "items.jsonl")}
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
            "span": [min(ordered), max(ordered)], "draft": g["draft"], "flag": g["flag"],
            "confirmed": g["confirmed"], "sample": [_clip(text[n]) for n in ordered[:3]],
        })
    rows.sort(key=lambda r: -r["oldest"])
    page, shown = _page(rows, args)
    return {**page, "groups": shown}


def themes(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    where = _where(st)
    text = {it["n"]: it["text"] for it in read_items(doc / "items.jsonl")}
    rows = []
    for t in _proposal(doc)["themes"]:
        ordered = oldest_first(t["items"])
        rows.append({
            "theme": t["id"], "size": len(ordered), "oldest": ordered[0], "span": [min(ordered), max(ordered)],
            "undecided": sum(where[n] == "undecided" for n in ordered),
            "sample": [_clip(text[n]) for n in ordered[:3]],
        })
    rows.sort(key=lambda r: -r["size"])
    page, shown = _page(rows, args)
    return {**page, "themes": shown}


def show(doc: Path, args) -> dict:
    st, _ = state.load(doc)
    items = read_items(doc / "items.jsonl")
    if args.group in st["groups"]:
        g = st["groups"][args.group]
        head = {"group": args.group, "name": g["name"], "draft": g["draft"], "flag": g["flag"], "confirmed": g["confirmed"]}
        inside = set(g["items"])
    else:
        found = [t for t in _proposal(doc)["themes"] if t["id"] == args.group]
        if not found:
            raise DistillError(f"no group or theme {args.group!r}")
        head = {"theme": args.group}
        inside = set(found[0]["items"])
    where = _where(st)
    by_n = {it["n"]: it for it in items}
    row = {it["n"]: i for i, it in enumerate(items)}
    distance = grouping.combined_distance(_vectors(doc, items), [it["text"] for it in items])
    inside_rows = [row[n] for n in inside]
    nearest = distance[inside_rows].min(axis=0)
    nearest[inside_rows] = np.inf
    ordered = oldest_first(inside)

    def line(n: int) -> dict:
        return {"n": n, "text": _clip(by_n[n]["text"]), "detail": by_n[n].get("detail"), "where": where[n]}

    return {
        **head, "size": len(ordered), "shown": min(len(ordered), args.limit),
        "items": [line(n) for n in ordered[: args.limit]],
        "nearest_outside": [
            {**line(items[i]["n"]), "distance": round(float(nearest[i]), 3)}
            for i in np.argsort(nearest)[:NEIGHBOURS] if np.isfinite(nearest[i])
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="folder holding one folder per document")
    sub = ap.add_subparsers(dest="command", required=True)
    for fn in (status, propose, groups, themes, show):
        p = sub.add_parser(fn.__name__)
        p.set_defaults(fn=fn)
        p.add_argument("id", help="document id, e.g. todo-001")
        if fn is propose:
            p.add_argument("--same-cut", type=float, default=grouping.SAME_CUT)
            p.add_argument("--theme-cut", type=float, default=grouping.THEME_CUT)
        if fn is show:
            p.add_argument("group", help="a group id (g12) or a proposed theme id (t3)")
            p.add_argument("--limit", type=int, default=50)
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
