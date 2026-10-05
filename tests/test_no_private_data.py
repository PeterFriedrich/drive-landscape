"""scripts/check_no_private_data.py — the guard itself, and the repo held to it."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_no_private_data", ROOT / "scripts/check_no_private_data.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

# Assembled so this file does not itself contain a link the guard would flag.
DOC_LINK = "https://docs.google." + "com/document/d/" + "x" * 30 + "/edit"
FOLDER_LINK = "https://drive.google." + "com/drive/folders/" + "y" * 30


def test_repo_tracks_no_private_data():
    assert guard.check() == []


@pytest.mark.parametrize("path", [
    "data/raw/inventory.json",
    "data/processed/items.txt",
    "output/graph.html",
    "data/raw/private/2026-01-02/manifest.json",
    "notebooks/files.jsonl.gz",
    "src/labels.csv",
    "credentials.json",
    "config/token.json",
    ".env",
])
def test_blocks_data_and_credential_paths(path):
    assert guard.check_file(path, b"x")


@pytest.mark.parametrize("path", ["data/DATA.md", "data/raw/.gitkeep", "src/inventory.py", "docs/SPEC_x.md"])
def test_allows_code_and_docs(path):
    assert guard.check_file(path, b"plain text\n") == []


@pytest.mark.parametrize("link", [DOC_LINK, FOLDER_LINK])
def test_blocks_drive_links_with_line_number(link):
    problems = guard.check_file("docs/notes.md", f"first line\nsee {link}\n".encode())
    assert len(problems) == 1 and "docs/notes.md:2:" in problems[0]


def test_blocks_large_files():
    assert guard.check_file("src/big.py", b"a" * (guard.MAX_BYTES + 1))
