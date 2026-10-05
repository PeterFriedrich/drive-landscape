"""src/inventory.py against a fake Drive service — no network, no Google libs, made-up names."""
import gzip
import json
from datetime import date

import pytest

from src import inventory

FOLDER = inventory.FOLDER
DOC = "application/vnd.google-apps.document"

FILES = [
    {"id": "root-a", "name": "folder a", "mimeType": FOLDER, "ownedByMe": True},
    {"id": "f1", "name": "doc one", "mimeType": DOC, "parents": ["root-a"], "ownedByMe": True, "size": "100"},
    {"id": "f2", "name": "doc two", "mimeType": DOC, "parents": ["root-a"], "ownedByMe": True, "trashed": True, "size": "50"},
    {"id": "f3", "name": "shared loose", "mimeType": DOC, "ownedByMe": False},
    {"id": "f4", "name": "shared in unseen folder", "mimeType": DOC, "parents": ["not-ours"], "ownedByMe": False},
]


class FakeService:
    def __init__(self, pages):
        self.pages = pages
        self.tokens = []

    def files(self):
        return self

    def list(self, **kw):
        self.tokens.append(kw["pageToken"])
        self._next = self.pages[len(self.tokens) - 1]
        return self

    def execute(self):
        return self._next


def test_list_files_follows_every_page():
    svc = FakeService([
        {"files": FILES[:2], "nextPageToken": "t1"},
        {"files": FILES[2:4], "nextPageToken": "t2"},
        {"files": FILES[4:]},
    ])
    assert [f["id"] for f in inventory.list_files(svc)] == [f["id"] for f in FILES]
    assert svc.tokens == [None, "t1", "t2"]


def test_list_files_refuses_incomplete_listing():
    svc = FakeService([{"files": FILES[:2], "incompleteSearch": True}])
    with pytest.raises(RuntimeError):
        list(inventory.list_files(svc))


def test_summarize_counts_orphans_and_shared_instead_of_dropping():
    s = inventory.summarize(FILES)
    assert s["total"] == 5
    assert s["folders"] == 1
    assert s["owned_by_me"] + s["not_owned_by_me"] == s["total"]
    assert s["trashed"] == 1
    assert s["no_parent"] == 2 and s["no_parent_owned_by_me"] == 1
    assert s["parent_not_in_inventory"] == 1
    assert s["bytes"] == 150
    assert sum(s["by_mime_type"].values()) == s["total"]


def test_write_snapshot_round_trips_every_row(tmp_path):
    dest = inventory.write_snapshot(FILES, tmp_path, date(2026, 1, 2))
    assert dest == tmp_path / "2026-01-02"
    with gzip.open(dest / "files.jsonl.gz", "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert rows == FILES
    assert json.loads((dest / "manifest.json").read_text())["total"] == len(FILES)
