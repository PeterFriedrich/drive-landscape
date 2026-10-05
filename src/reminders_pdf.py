"""Turn an Apple Reminders PDF export into one row per reminder.

    python -m src.reminders_pdf LIST.pdf --out data/raw/private/todo/todo-001

Writes <out>/items.jsonl (one reminder per line) and <out>/list.md (the same
list as a Markdown checklist, for reading). Both are private — see data/DATA.md.

How the export is laid out (iOS 18 "Print" from Reminders): each reminder has a
small square-bounded marker in the left margin and its title beside it at one
font size; a long title wraps onto unmarked lines below; a subtask's marker is
indented; a smaller line under a reminder is its date; the smallest lines are
page footers; the largest line is the list name and its item count.

The export draws every marker the same, so done / not-done cannot be read from it.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
from pathlib import Path

log = logging.getLogger("reminders_pdf")

MARKER_SIDE = (8, 14)   # points; the marker's bounding box is about 11 x 11
TITLE_MIN_SIZE = 15.0   # the list name is ~19 pt, a reminder ~11 pt
SAME_ROW = 4.0          # a marker belongs to the line whose mid-height is this close


def read_pages(path: Path) -> list[dict]:
    """Per page: text lines and markers as plain dicts. Import is local so tests need no PDF library."""
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = []
            for ln in page.extract_text_lines(return_chars=True):
                chars = [c for c in ln["chars"] if c["text"].strip()]
                if not chars:
                    continue
                bold = ["Bold" in c["fontname"] for c in chars]
                lines.append({
                    "text": ln["text"].strip(),
                    "bold_text": "".join(c["text"] for c in ln["chars"] if "Bold" in c["fontname"]).strip(),
                    "x0": ln["x0"], "top": ln["top"], "bottom": ln["bottom"],
                    "size": statistics.median(c["size"] for c in chars),
                    "bold": all(bold),
                })
            markers = [
                {"x0": r["x0"], "top": r["top"], "bottom": r["bottom"]}
                for r in page.rects
                if MARKER_SIDE[0] <= r["width"] <= MARKER_SIDE[1] and MARKER_SIDE[0] <= r["height"] <= MARKER_SIDE[1]
            ]
            pages.append({"lines": lines, "markers": markers})
    return pages


def _mid(o: dict) -> float:
    return (o["top"] + o["bottom"]) / 2


def group(pages: list[dict]) -> dict:
    """Assemble reminders from lines and markers.

    Nothing is dropped quietly: every line ends up in an item, the title, the
    footer count or ``unplaced``; every marker is used or counted in
    ``markers_without_text``.
    """
    all_lines = [ln for p in pages for ln in p["lines"]]
    marked_sizes = [
        ln["size"] for p in pages for ln in p["lines"]
        if any(abs(_mid(m) - _mid(ln)) < SAME_ROW for m in p["markers"])
    ]
    out = {"title": None, "stated_count": None, "items": [], "footer_lines": 0,
           "unplaced": [], "markers_without_text": 0, "pages": len(pages), "lines": len(all_lines)}
    if not marked_sizes:
        out["unplaced"] = [{"page": n, "text": ln["text"]} for n, p in enumerate(pages, 1) for ln in p["lines"]]
        return out
    item_size = statistics.median(marked_sizes)
    base_x = min(m["x0"] for p in pages for m in p["markers"])
    indent = min((ln["x0"] for ln in all_lines if abs(ln["size"] - item_size) < 0.3), default=0) - base_x or 1

    items = out["items"]
    parents: list[int] = []  # item number at each level above the current one
    for page_no, page in enumerate(pages, 1):
        used = set()
        for ln in sorted(page["lines"], key=lambda l: l["top"]):
            marker = next((i for i, m in enumerate(page["markers"])
                           if i not in used and abs(_mid(m) - _mid(ln)) < SAME_ROW), None)
            if ln["size"] >= TITLE_MIN_SIZE and marker is None:
                if out["title"] is None:
                    out["title"] = ln["bold_text"] or ln["text"]
                    rest = ln["text"].replace(out["title"], "", 1).strip().replace(",", "")
                    out["stated_count"] = int(rest) if rest.isdigit() else None
                else:
                    out["unplaced"].append({"page": page_no, "text": ln["text"]})
            elif marker is not None:
                used.add(marker)
                level = round((page["markers"][marker]["x0"] - base_x) / indent)
                del parents[level:]
                items.append({"n": len(items) + 1, "level": level, "parent": parents[-1] if parents else None,
                              "text": ln["text"], "detail": None, "bold": ln["bold"], "page": page_no})
                parents.append(items[-1]["n"])
            elif ln["size"] < item_size - 2:
                out["footer_lines"] += 1
            elif not items:
                out["unplaced"].append({"page": page_no, "text": ln["text"]})
            elif abs(ln["size"] - item_size) < 0.3:
                items[-1]["text"] += " " + ln["text"]  # a wrapped title, possibly over a page break
            else:
                last = items[-1]
                last["detail"] = ln["text"] if last["detail"] is None else last["detail"] + " " + ln["text"]
        out["markers_without_text"] += len(page["markers"]) - len(used)
    return out


def to_markdown(parsed: dict) -> str:
    lines = [f"# {parsed['title'] or 'Reminders'}", ""]
    for it in parsed["items"]:
        text = f"**{it['text']}**" if it["bold"] else it["text"]
        detail = f" _({it['detail']})_" if it["detail"] else ""
        lines.append(f"{'  ' * it['level']}- [ ] {text}{detail}")
    return "\n".join(lines) + "\n"


def summarize(parsed: dict) -> dict:
    items = parsed["items"]
    top = sum(it["level"] == 0 for it in items)
    return {
        "pages": parsed["pages"], "lines": parsed["lines"], "items": len(items),
        "top_level": top, "subtasks": len(items) - top,
        "with_detail": sum(it["detail"] is not None for it in items),
        "footer_lines": parsed["footer_lines"], "unplaced_lines": len(parsed["unplaced"]),
        "markers_without_text": parsed["markers_without_text"],
        "stated_count": parsed["stated_count"],
        "stated_count_matches": None if parsed["stated_count"] is None
        else parsed["stated_count"] in (top, len(items)),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="directory for items.jsonl and list.md")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    parsed = group(read_pages(args.pdf))
    summary = summarize(parsed)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "items.jsonl").open("w", encoding="utf-8") as fh:
        for it in parsed["items"]:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    (args.out / "list.md").write_text(to_markdown(parsed), encoding="utf-8")
    (args.out / "extract_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    log.info("wrote %s %s", args.out, json.dumps(summary))
    bad = summary["unplaced_lines"] or summary["markers_without_text"] or summary["stated_count_matches"] is False
    if bad:
        log.error("extraction is incomplete or disagrees with the list's own count — check before using")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
