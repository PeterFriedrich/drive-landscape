"""The owner's review page for one document, served on this machine only.

    python -m src.ui todo-001 [--port 8377]

Serves web/review.html and a small JSON API on 127.0.0.1. Every action on the
page is one line appended to the log through src/state.py, signed "owner", and
the page then reads the state again. Nothing here holds state of its own.

    GET  /                      the page
    GET  /api/state             counts, themes, groups and items as they stand
    GET  /api/neighbours?item=N the item's nearest neighbours (src.distill show)
    POST /api/log               one log entry without "who"; new groups and themes get an id
    POST /api/save              commit the log in the repository that holds the document, and push it

The responses carry item text, which is private — see data/DATA.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src import distill, state
from src.embed import read_items

log = logging.getLogger("ui")

PAGE = Path(__file__).resolve().parent.parent / "web" / "review.html"
PORT = 8377
NEW_ID = {"create": ("group", "g"), "split": ("new", "g"), "theme": ("theme", "t")}
LOG = "work/log.jsonl"


def _git(doc: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(doc), *args], capture_output=True, text=True, timeout=60)


def unsaved(doc: Path) -> bool | None:
    """Whether the log holds decisions its repository's remote does not have. None outside a repository."""
    changed = _git(doc, "status", "--porcelain", "--", LOG)
    if changed.returncode:
        return None
    ahead = _git(doc, "rev-list", "--count", "@{u}..HEAD", "--", LOG)
    return bool(changed.stdout.strip()) or ahead.stdout.strip() not in ("", "0")


def save(doc: Path) -> dict:
    """Commit the log and push it. Only the owner's Save button does this; nothing commits on its own."""
    if _git(doc, "rev-parse", "--git-dir").returncode:
        raise ValueError(f"{doc} is not in a git repository, so there is nowhere to save to")
    _, c = state.load(doc)  # a log that does not replay is not committed
    _git(doc, "add", "--", LOG)
    committed = _git(doc, "diff", "--cached", "--quiet", "--", LOG).returncode == 1
    if committed:
        message = (f"{doc.name}: decisions from the review page ({c['kept']} kept, {c['dropped']} dropped, "
                   f"{c['broken']} split, {c['groups_confirmed']} groups and {c['themes_confirmed']} themes confirmed)")
        done = _git(doc, "commit", "-q", "-m", message, "--", LOG)
        if done.returncode:
            raise ValueError(f"git commit failed: {done.stderr.strip() or done.stdout.strip()}")
    try:
        push = _git(doc, "push", "-q")
        error = push.stderr.strip() if push.returncode else None
    except subprocess.TimeoutExpired:
        error = "git push took more than 60 seconds"
    return {"committed": committed, "pushed": error is None, "error": error}


def snapshot(doc: Path) -> dict:
    st, counts = state.load(doc)
    where = distill._where(st)
    theme_of_group = {gid: tid for tid, t in st["themes"].items() for gid in t["groups"]}
    theme_of_item = {n: tid for tid, t in st["themes"].items() for n in t["items"]}
    items = {}
    originals = read_items(doc / "items.jsonl")
    for it in originals + [{"n": pid, "text": text} for pid, text in st["parts"].items()]:
        n = it["n"]
        if n in st["broken"]:
            continue
        split = distill.sentences(it["text"])
        items[str(n)] = {
            "n": n, "text": it["text"], "detail": it.get("detail"), "where": where[n],
            "theme": theme_of_item.get(n, theme_of_group.get(where[n])),
            "split": split if len(split) > 1 else None,
            "reason": st["dropped"].get(n),
            "confirmed": st["kept"].get(n, {}).get("confirmed", False),
        }
    return {
        "doc": doc.name,
        "unsaved": unsaved(doc),
        "counts": counts,
        "themes": [{"id": tid, **t} for tid, t in st["themes"].items()],
        "groups": {gid: {**g, "theme": theme_of_group.get(gid)} for gid, g in st["groups"].items()},
        "items": items,
    }


def record(doc: Path, entry: dict) -> dict:
    """Append the owner's decision; a new group or theme gets the next free id."""
    entry = {k: v for k, v in entry.items() if k not in ("who", "when")}
    if entry.get("op") in NEW_ID:
        key, prefix = NEW_ID[entry["op"]]
        entry[key] = distill._next_id(doc, prefix)
    return state.append(doc, {"who": "owner", **entry})


def handler(doc: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def send(self, code: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def answer(self, fn) -> None:
            try:
                self.send(200, json.dumps(fn(), ensure_ascii=False).encode())
            except (state.LogError, distill.DistillError, ValueError, KeyError) as exc:
                self.send(400, json.dumps({"error": str(exc)}).encode())

        def local(self) -> bool:
            # A page on another site can make this browser call 127.0.0.1; it cannot make it send our Host.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host in ("127.0.0.1", "localhost"):
                return True
            self.send(403, b'{"error": "this page is served on 127.0.0.1 only"}')
            return False

        def do_GET(self) -> None:
            if not self.local():
                return
            url = urlparse(self.path)
            if url.path == "/":
                self.send(200, PAGE.read_bytes(), "text/html")
            elif url.path == "/api/state":
                self.answer(lambda: snapshot(doc))
            elif url.path == "/api/neighbours":
                item = parse_qs(url.query).get("item", [""])[0]
                self.answer(lambda: distill.show(doc, argparse.Namespace(group=item, limit=1)))
            else:
                self.send(404, b'{"error": "not found"}')

        def do_POST(self) -> None:
            if not self.local():
                return
            # A cross-site form cannot send JSON without a preflight, which is never answered here.
            if self.path not in ("/api/log", "/api/save") or self.headers.get("Content-Type") != "application/json":
                self.send(404, b'{"error": "not found"}')
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.path == "/api/save":
                self.answer(lambda: save(doc))
            else:
                self.answer(lambda: {"logged": record(doc, json.loads(body))})

        def log_message(self, fmt: str, *args) -> None:
            log.info("%s %s", self.command, self.path.split("?")[0])

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("id", help="document id, e.g. todo-001")
    ap.add_argument("--root", type=Path, default=distill.ROOT, help="folder holding one folder per document")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    doc = args.root / args.id
    state.load(doc)  # fail now, not on the first click
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(doc))
    log.info("review page for %s at http://127.0.0.1:%d/  (Ctrl-C to stop)", args.id, server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
