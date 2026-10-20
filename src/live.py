"""The live inbox: one Google Doc the owner types paper notes into, organized on demand.

    python -m src.live create "Notes"           (once: the app makes the doc)
    python -m src.live pull                     (snapshot it; print the Inbox lines)
    python -m src.live push FILE [--accept-missing] [--yes]

The doc is an organized list on top and an `Inbox` heading at the bottom; the
owner types only under Inbox. `pull` exports the doc as Markdown, saves it to
<out>/snapshots/ and prints what is under Inbox. The session then writes
the proposal: the organized part with the Inbox lines sorted in, no Inbox
heading, in FILE. `push` without --yes is a dry run (the diff and what would be lost);
with --yes it writes FILE plus an empty Inbox back to the doc.

push refuses when the doc changed since the pull (the owner may be typing), and
when a line of the pulled doc is missing from the proposal unless
--accept-missing, which records those lines in pushes.jsonl. Scope is
drive.file: the app can open only the doc it created, nothing else in Drive.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from src.inventory import DEFAULT_CONFIG_DIR, build_service

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
DOC = "application/vnd.google-apps.document"
MD = "text/markdown"
DEFAULT_OUT = Path("data/raw/private/live")

INBOX = re.compile(r"^#{1,6}\s*\**inbox\**\s*$", re.IGNORECASE)
HEADING = re.compile(r"^#{1,6}\s")
# Bullets, numbering and checkboxes as Docs exports them; the text after them is the item.
MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")


def split_inbox(text: str) -> tuple[str, list[str]]:
    """(organized part, Inbox lines). No Inbox heading means everything is organized."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if INBOX.match(line.strip()):
            return "\n".join(lines[:i]).rstrip() + "\n", items("\n".join(lines[i + 1:]))
    return text, []


def norm(line: str) -> str:
    text = MARKER.sub("", line).strip()
    return re.sub(r"\s+", " ", text.replace("\\", "")).casefold()


def items(text: str) -> list[str]:
    """Every non-blank, non-heading line, as written (markers stripped)."""
    return [MARKER.sub("", l).strip() for l in text.splitlines() if l.strip() and not HEADING.match(l.strip())]


def missing(pulled: str, proposal: str) -> list[str]:
    """Lines of the pulled doc (both parts) that the proposal does not carry."""
    organized, inbox = split_inbox(pulled)
    have = {norm(l) for l in items(proposal)}
    return [l for l in items(organized) + inbox if norm(l) not in have]


def with_inbox(proposal: str) -> str:
    return proposal.rstrip() + "\n\n# Inbox\n"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def export(service, doc_id: str) -> str:
    data = service.files().export(fileId=doc_id, mimeType=MD).execute()
    return data.decode("utf-8") if isinstance(data, bytes) else data


def version(service, doc_id: str) -> str:
    return service.files().get(fileId=doc_id, fields="version").execute()["version"]


def upload(text: str):
    from googleapiclient.http import MediaInMemoryUpload
    return MediaInMemoryUpload(text.encode("utf-8"), mimetype=MD)


def create(service, out: Path, title: str, media=upload) -> dict:
    if (out / "doc.json").exists():
        raise SystemExit(f"{out / 'doc.json'} exists: the live doc is already made")
    f = service.files().create(
        body={"name": title, "mimeType": DOC}, media_body=media(with_inbox("")), fields="id,webViewLink"
    ).execute()
    out.mkdir(parents=True, exist_ok=True)
    (out / "doc.json").write_text(json.dumps({"id": f["id"], "created": stamp()}, indent=2) + "\n")
    return {"created": f["id"], "link": f.get("webViewLink")}


def pull(service, out: Path) -> dict:
    doc_id = json.loads((out / "doc.json").read_text())["id"]
    ver = version(service, doc_id)
    text = export(service, doc_id)
    snap = out / "snapshots" / f"{stamp()}.md"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(text)
    (out / "last_pull.json").write_text(json.dumps({"snapshot": snap.name, "version": ver}, indent=2) + "\n")
    organized, inbox = split_inbox(text)
    return {"snapshot": str(snap), "organized_lines": len(items(organized)), "inbox": inbox}


def push(service, out: Path, proposal: str, accept_missing: bool, yes: bool, media=upload) -> dict:
    doc_id = json.loads((out / "doc.json").read_text())["id"]
    last = json.loads((out / "last_pull.json").read_text())
    pulled = (out / "snapshots" / last["snapshot"]).read_text()
    if split_inbox(proposal)[1]:
        raise SystemExit("the proposal still has lines under Inbox; sort them in first")
    proposal = split_inbox(proposal)[0]
    lost = missing(pulled, proposal)
    diff = list(difflib.unified_diff(pulled.splitlines(), with_inbox(proposal).splitlines(), "doc", "proposal", lineterm=""))
    report = {"missing": lost, "diff": diff}
    if lost and not accept_missing:
        return {**report, "refused": "lines of the doc are missing from the proposal; pass --accept-missing to drop them"}
    if not yes:
        return {**report, "dry_run": True}
    if version(service, doc_id) != last["version"]:
        return {**report, "refused": "the doc changed since the pull; pull again"}
    service.files().update(fileId=doc_id, media_body=media(with_inbox(proposal))).execute()
    back = export(service, doc_id)
    snap = out / "snapshots" / f"{stamp()}-pushed.md"
    snap.write_text(back)
    (out / "last_pull.json").write_text(
        json.dumps({"snapshot": snap.name, "version": version(service, doc_id)}, indent=2) + "\n"
    )
    # The doc's Markdown import is Google's; say so if the round trip did not keep every line.
    not_kept = missing(with_inbox(proposal), back)
    with (out / "pushes.jsonl").open("a") as fh:
        fh.write(json.dumps({"at": stamp(), "from": last["snapshot"], "to": snap.name, "dropped": lost,
                             "not_kept_by_drive": not_kept}, ensure_ascii=False) + "\n")
    return {"pushed": snap.name, "dropped": lost, "not_kept_by_drive": not_kept}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("create").add_argument("title")
    sub.add_parser("pull")
    p = sub.add_parser("push")
    p.add_argument("proposal", type=Path)
    p.add_argument("--accept-missing", action="store_true")
    p.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    # Its own token: inventory's stays read-only.
    service = build_service(args.config_dir, SCOPES, "token-live.json")
    if args.command == "create":
        out = create(service, args.out, args.title)
    elif args.command == "pull":
        out = pull(service, args.out)
    else:
        out = push(service, args.out, args.proposal.read_text(), args.accept_missing, args.yes)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if "refused" in out else 0


if __name__ == "__main__":
    raise SystemExit(main())
