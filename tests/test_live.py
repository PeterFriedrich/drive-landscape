"""src/live.py against a fake Drive doc — no network, no Google libs, made-up notes."""
import json

import pytest

from src import live


class Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeDrive:
    """One Google Doc held as Markdown; every write bumps its version, as Drive does."""

    def __init__(self, text=""):
        self.text, self.ver = text, 1

    def files(self):
        return self

    def owner_types(self, text):
        self.text, self.ver = text, self.ver + 1

    def create(self, body, media_body, fields):
        self.text = media_body
        return Call(lambda: {"id": "doc-x", "webViewLink": "made-up"})

    def export(self, fileId, mimeType):
        return Call(lambda: self.text.encode())

    def get(self, fileId, fields):
        return Call(lambda: {"version": str(self.ver)})

    def update(self, fileId, media_body):
        def run():
            self.owner_types(media_body)
            return {}
        return Call(run)


def plain(text):
    return text


DOC = """# Garden
* buy seeds
* fix the hose

# Inbox
* call the plumber
* buy seeds
"""


@pytest.fixture
def setup(tmp_path):
    drive = FakeDrive()
    live.create(drive, tmp_path, "notes", media=plain)
    drive.owner_types(DOC)
    return drive, tmp_path


def test_create_makes_a_doc_with_an_empty_inbox_and_refuses_a_second(tmp_path):
    drive = FakeDrive()
    live.create(drive, tmp_path, "notes", media=plain)
    assert live.split_inbox(drive.text) == ("\n", [])
    assert "# Inbox" in drive.text
    with pytest.raises(SystemExit):
        live.create(drive, tmp_path, "notes", media=plain)


def test_pull_snapshots_the_doc_and_returns_the_inbox_lines(setup):
    drive, out = setup
    got = live.pull(drive, out)
    assert got["inbox"] == ["call the plumber", "buy seeds"]
    assert got["organized_lines"] == 2
    assert (out / "snapshots" / json.loads((out / "last_pull.json").read_text())["snapshot"]).read_text() == DOC


def test_markers_checkboxes_and_case_do_not_make_a_line_new():
    assert live.norm("- [x] Buy  Seeds") == live.norm("* buy seeds") == live.norm("1. buy seeds")


def test_push_refuses_a_proposal_that_loses_a_line_unless_accepted(setup):
    drive, out = setup
    live.pull(drive, out)
    proposal = "# Garden\n* buy seeds\n* fix the hose\n"  # "call the plumber" left out
    got = live.push(drive, out, proposal, accept_missing=False, yes=True, media=plain)
    assert got["missing"] == ["call the plumber"] and "refused" in got
    assert drive.text == DOC

    got = live.push(drive, out, proposal, accept_missing=True, yes=True, media=plain)
    assert got["dropped"] == ["call the plumber"]
    assert json.loads((out / "pushes.jsonl").read_text())["dropped"] == ["call the plumber"]


def test_a_duplicate_inbox_line_is_carried_by_the_existing_one(setup):
    drive, out = setup
    live.pull(drive, out)
    proposal = "# Garden\n* buy seeds\n* fix the hose\n\n# House\n* call the plumber\n"
    got = live.push(drive, out, proposal, accept_missing=False, yes=True, media=plain)
    assert got["dropped"] == [] and got["not_kept_by_drive"] == []
    assert live.split_inbox(drive.text) == (proposal.rstrip() + "\n", [])


def test_push_without_yes_is_a_dry_run(setup):
    drive, out = setup
    live.pull(drive, out)
    got = live.push(drive, out, "# Garden\n* buy seeds\n* fix the hose\n* call the plumber\n",
                    accept_missing=False, yes=False, media=plain)
    assert got["dry_run"] and got["diff"]
    assert drive.text == DOC


def test_push_refuses_when_the_owner_edited_since_the_pull(setup):
    drive, out = setup
    live.pull(drive, out)
    drive.owner_types(DOC + "* typed while organizing\n")
    got = live.push(drive, out, "# Garden\n* buy seeds\n* fix the hose\n* call the plumber\n",
                    accept_missing=False, yes=True, media=plain)
    assert "refused" in got
    assert "typed while organizing" in drive.text


def test_push_refuses_a_proposal_with_lines_still_under_inbox(setup):
    drive, out = setup
    live.pull(drive, out)
    with pytest.raises(SystemExit):
        live.push(drive, out, DOC, accept_missing=False, yes=True, media=plain)
