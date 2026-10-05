"""Guards on the LOADED PATH — what every session is told to read before it works.

`CLAUDE.md` names the files a session must open: itself, `TODO.md`, the latest
handoff, the auto-memory index. The handoff pile stays a small share of that
only while the archive discipline holds: *"keep the 3 most recent at top level,
archive older"* is a rule with a reader and no check unless this file exists,
and a lapse is silent and compounding — nobody notices the 4th file.

Lives in `tests/` rather than as a `scripts/check_*.py` because it needs no CLI,
no report and no exit code of its own — it is a repo invariant, and pytest
already runs on the merge gate.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUMMARIES = REPO / "session-summary"

# CLAUDE.md, "Token Efficiency": read only the latest, keep the 3 most recent.
MAX_LIVE = 3


def _live() -> list[str]:
    return sorted(p.name for p in SUMMARIES.glob("*.md"))


def _archived() -> list[str]:
    return sorted(p.name for p in (SUMMARIES / "archive").glob("*.md"))


def test_at_most_three_handoffs_at_top_level():
    live = _live()
    assert len(live) <= MAX_LIVE, (
        f"{len(live)} handoffs at session-summary/ top level, max {MAX_LIVE} "
        f"(CLAUDE.md). Move the oldest into session-summary/archive/ in this same "
        f"PR — `git mv session-summary/{live[0]} session-summary/archive/`. "
        f"Archiving is not deletion: the files stay, out of the loaded path."
    )


def test_the_live_handoffs_are_the_most_recent_ones():
    """Not just three — the three NEWEST. Filenames are date-prefixed, so every
    archived name must sort before every live one. Catches archiving the wrong
    end, which passes the count test while leaving a stale file in the path a
    session is told to read."""
    live, archived = _live(), _archived()
    if not live or not archived:
        return
    assert archived[-1] < live[0], (
        f"session-summary/archive/{archived[-1]} is newer than the live "
        f"{live[0]} — the wrong end was archived. The top-level files must be "
        f"the {MAX_LIVE} most recent."
    )


def test_archive_is_never_deleted_from():
    """A floor under the two tests above: both pass over a repo that DELETED its
    history instead of moving it. A young repo (no archive yet) and a repo that
    emptied its archive look identical on disk, so ask git: no file under
    `session-summary/archive/` may ever have been deleted. `-M` so a rename
    (re-dating a file) is not read as a deletion. Fails open without git or
    history (a shallow CI checkout sees nothing — tests.yml uses fetch-depth 0
    for this reason)."""
    try:
        out = subprocess.run(
            ["git", "log", "-M", "--diff-filter=D", "--name-only", "--format=",
             "--", "session-summary/archive/"],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if out.returncode != 0:
        return  # not a git checkout: nothing to check
    deleted = [ln for ln in out.stdout.splitlines() if ln.strip()]
    assert not deleted, (
        f"{len(deleted)} file(s) were DELETED from session-summary/archive/ "
        f"(e.g. {deleted[0]}). The archive is append-only: it is the only copy "
        f"of what earlier sessions did. Restore them."
    )
