"""Tests for the merged-branch reminder in scripts/handoff_gap.py.

Ported with the reminder from edmonton-tax-viz (its PR #727), whose
tests/test_handoff_gap.py also covers the handoff-gap half; that half is not
ported here yet. The reminder must stay silent below the threshold, count only
merged branches, and stay out of SessionEnd.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import handoff_gap as hg  # noqa: E402


def _run(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real git repo — the script shells out, so a fake would test nothing."""
    _run(tmp_path, "init", "-q", "-b", "main")
    _run(tmp_path, "config", "user.email", "t@example.com")
    _run(tmp_path, "config", "user.name", "T")
    (tmp_path / "session-summary").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "session-summary" / "2026-09-16-s1.md").write_text("# handoff\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "handoff")
    monkeypatch.setattr(hg, "ROOT", tmp_path)
    monkeypatch.setattr(hg, "SUMMARIES", tmp_path / "session-summary")
    return tmp_path


def _commit(repo, path, text="x", msg="work"):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", msg)


# --- the two that carry the design -------------------------------------------


def _origin(repo, merged=0, unmerged=0):
    """Fake remote-tracking refs: no remote is needed, only the refs."""
    _run(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
    for i in range(merged):
        _run(repo, "update-ref", f"refs/remotes/origin/docs/m{i}", "HEAD")
    if unmerged:
        _run(repo, "checkout", "-q", "-b", "side")
        (repo / "docs" / "side.md").write_text("x")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-qm", "side")
        for i in range(unmerged):
            _run(repo, "update-ref", f"refs/remotes/origin/docs/u{i}", "HEAD")
        _run(repo, "checkout", "-q", "main")


def test_branch_reminder_is_silent_one_below_the_threshold(repo, capsys):
    _origin(repo, merged=hg.BRANCH_REMINDER_AT - 1)
    assert hg.merged_branch_reminder() is None
    assert hg.main(["--session-start"]) == 0
    assert capsys.readouterr().out == ""


def test_branch_reminder_fires_at_the_threshold_with_the_count(repo, capsys):
    _origin(repo, merged=hg.BRANCH_REMINDER_AT)
    assert f"{hg.BRANCH_REMINDER_AT} merged branches" in hg.merged_branch_reminder()
    hg.main(["--session-start"])
    out = json.loads(capsys.readouterr().out)
    assert "merged branches" in out["hookSpecificOutput"]["additionalContext"]
    # no handoff gap exists here, so the handoff sentence must not appear
    assert "handoff" not in out["hookSpecificOutput"]["additionalContext"]


def test_branch_reminder_does_not_count_unmerged_branches(repo):
    _origin(repo, merged=hg.BRANCH_REMINDER_AT - 1, unmerged=5)
    assert hg.merged_branch_reminder() is None


def test_branch_reminder_without_origin_master_is_silent(repo):
    assert hg.merged_branch_reminder() is None


def test_branch_reminder_stays_out_of_session_end(repo, capsys):
    _origin(repo, merged=hg.BRANCH_REMINDER_AT)
    assert hg.main(["--session-end"]) == 0
    io = capsys.readouterr()
    assert io.out == "" and io.err == ""


def test_branch_reminder_and_handoff_gap_are_both_reported(repo, capsys):
    _origin(repo, merged=hg.BRANCH_REMINDER_AT)
    _commit(repo, "src/a.py")
    hg.main(["--session-start"])
    text = json.loads(capsys.readouterr().out)["systemMessage"]
    assert "merged branches" in text and "that handoff records none of it" in text
