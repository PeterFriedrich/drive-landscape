"""Keep Drive data out of this repo. This repo is code; data lives in the private repo.

Checks every tracked file (or, with ``--staged``, every file in the index):

  1. nothing under ``data/`` or ``output/`` except the allow-list below;
  2. no data-shaped or credential files anywhere (by name);
  3. no file over ``MAX_BYTES``;
  4. no Google Drive / Docs link in any text file — a link carries a file id.

It cannot recognise a private file *name* or todo text typed into a doc; that
rule (CLAUDE.md "Project") still rests on the author.

Run by ``.githooks/pre-commit`` (``--staged``) and by ``tests/test_no_private_data.py``
on the merge gate. Exit codes: 0 ok; 7 a violation.

Usage:
    python scripts/check_no_private_data.py            # tracked files
    python scripts/check_no_private_data.py --staged   # the index
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXIT_OK = 0
EXIT_FAIL = 7

DATA_DIRS = ("data/", "output/")
ALLOWED_IN_DATA = {"data/DATA.md", "data/raw/.gitkeep", "data/processed/.gitkeep", "output/.gitkeep"}
DATA_SUFFIXES = (
    ".jsonl", ".gz", ".zip", ".csv", ".tsv", ".parquet", ".npy", ".npz", ".pkl",
    ".sqlite", ".db", ".xlsx", ".docx", ".pdf", ".geojson",
)
CREDENTIAL_NAMES = {"credentials.json", "token.json", "client_secret.json"}
MAX_BYTES = 500_000
DRIVE_LINK = re.compile(
    r"(?:docs\.google\.com/(?:document|spreadsheets|presentation|forms|drawings)/d/"
    r"|drive\.google\.com/(?:file/d/|drive/(?:u/\d+/)?folders/|open\?id=|uc\?))[\w-]{10,}"
)


def git(*args: str, root: Path = ROOT) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def paths(staged: bool, root: Path = ROOT) -> list[str]:
    cmd = ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"] if staged else ["ls-files", "-z"]
    return [p for p in git(*cmd, root=root).decode().split("\0") if p]


def content(path: str, staged: bool, root: Path = ROOT) -> bytes:
    return git("show", f":{path}", root=root) if staged else (root / path).read_bytes()


def check_file(path: str, blob: bytes) -> list[str]:
    out = []
    name = path.rsplit("/", 1)[-1]
    if path.startswith(DATA_DIRS) and path not in ALLOWED_IN_DATA:
        out.append(f"{path}: under a data directory — data belongs in the private repo (data/raw/private/)")
    if name.lower().endswith(DATA_SUFFIXES):
        out.append(f"{path}: data-shaped file ({name.rsplit('.', 1)[-1]})")
    if name in CREDENTIAL_NAMES or name == ".env" or name.startswith(".env."):
        out.append(f"{path}: credential file")
    if len(blob) > MAX_BYTES:
        out.append(f"{path}: {len(blob):,} bytes, over the {MAX_BYTES:,} limit")
    if b"\0" not in blob[:8192]:
        for n, line in enumerate(blob.decode("utf-8", errors="replace").splitlines(), 1):
            if DRIVE_LINK.search(line):
                out.append(f"{path}:{n}: Google Drive/Docs link (carries a file id)")
    return out


def check(staged: bool = False, root: Path = ROOT) -> list[str]:
    problems = []
    for p in paths(staged, root):
        if not staged and not (root / p).is_file():
            continue  # deleted in the working tree, or a submodule
        problems += check_file(p, content(p, staged, root))
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staged", action="store_true", help="check the index instead of tracked files")
    args = ap.parse_args(argv)
    problems = check(args.staged)
    for p in problems:
        print(f"PRIVATE-DATA GUARD: {p}", file=sys.stderr)
    if problems:
        print("Blocked. This repo is public code; see data/DATA.md \"Where the data lives\".", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
