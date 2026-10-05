"""Guards on the Claude web brief (`scripts/make_brief.py`, `docs/CLAUDE_WEB.md`).

The committed `docs/BRIEF.md` is what a claude.ai Project syncs. It is only
worth syncing if it matches the repo, so the first test fails the merge gate
when it is stale. The rest pin what the generator keeps and drops, each against
a fixture repo, so a parser that quietly stops matching fails here instead of
producing a brief with an empty section.
"""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("make_brief", REPO / "scripts" / "make_brief.py")
make_brief = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_brief)


def test_committed_brief_is_current():
    target = REPO / make_brief.BRIEF
    if not target.exists():
        pytest.skip("no docs/BRIEF.md committed (private repo: the brief is pasted, not synced)")
    assert target.read_text(encoding="utf-8") == make_brief.build(REPO), (
        "docs/BRIEF.md is stale — its sources changed since it was generated. "
        "Run `python scripts/make_brief.py --write` and commit it in this PR."
    )


def _fixture(root: Path) -> Path:
    (root / "docs").mkdir()
    (root / "CLAUDE.md").write_text(
        "# Claude Instructions\n\n## Project\nToy fiscal analysis.\n\n"
        "## Key Files\n- `TODO.md` — the backlog. Read it first.\n"
        "- `docs/SPIKE.md` — the spike on St. Albert parcels. Details.\n\n## Other\nx\n")
    (root / "TODO.md").write_text(
        "# TODO\n\n## Open work\n\n### Group one\n\n"
        "- [ ] **Open item.** First line\n  continues here.\n"
        "  - [ ] a nested child, not a top-level item\n"
        "- [x] **Closed but not yet archived.**\n\n## Done\n\n- [x] **Archived.**\n")
    (root / "docs" / "DECISIONS.md").write_text(
        "# Decisions\n\n| When | Decision | Full reasoning |\n|---|---|---|\n"
        "| 2026-09-01 | ~~**Old rule**~~ SUPERSEDED 2026-09-02 | `docs/X.md` |\n"
        "| 2026-09-02 | **New rule.** Long tail sentence. | `docs/X.md` |\n"
        "| 2026-09-03 | **Parked on St. Albert licensing.** Middle sentence. "
        "Rejected: scraping it anyway. | `docs/X.md` |\n"
        "| 2026-09-04 | **Keep the flag.** Why. The `x`-rejected clause stays. | `docs/X.md` |\n")
    (root / "docs" / "SCOPE.md").write_text("# SCOPE\n\n## Out of scope\n\n- **Rasters.** No GIS.\n")
    (root / "requirements.txt").write_text("# comment\npandas==2.3.0\n")
    return root


def test_brief_carries_each_source(tmp_path):
    brief = make_brief.build(_fixture(tmp_path))
    for expected in ("Toy fiscal analysis.", "**Rasters.** No GIS.", "pandas==2.3.0",
                     "**New rule.**", "**Open item.** First line continues here.",
                     "**Group one**", "`TODO.md` — the backlog", "CLAIM-CHECK"):
        assert expected in brief, expected


def test_brief_drops_dead_and_closed_rows(tmp_path):
    brief = make_brief.build(_fixture(tmp_path))
    for dropped in ("Old rule", "Closed but not yet archived", "Archived.",
                    "nested child", "Long tail sentence", "Middle sentence", "`x`-rejected"):
        assert dropped not in brief, dropped


def test_decision_keeps_its_rejected_sentence_and_survives_st(tmp_path):
    """Two bugs alberta-regional-viz found (2026-09-30), fixed first in
    edmonton-tax-viz: the summary was the first sentence only, so "Rejected:"
    clauses were lost, and the sentence split cut "St. Albert" to "St."."""
    brief = make_brief.build(_fixture(tmp_path))
    assert "**Parked on St. Albert licensing.** … Rejected: scraping it anyway." in brief


def test_doc_map_survives_st_and_clipped_decision_has_one_ellipsis(tmp_path):
    """Reported by alberta-regional-viz (2026-10-01): the doc map split on its
    own regex, cutting "St. Albert" to "St", and a clipped first sentence plus
    a rejected sentence rendered "… … Rejected"."""
    root = _fixture(tmp_path)
    decisions = root / "docs" / "DECISIONS.md"
    decisions.write_text(decisions.read_text() + "| 2026-09-05 | **"
                         + "word " * 60 + "end.** Rejected: the short one. | `docs/X.md` |\n")
    brief = make_brief.build(root)
    assert "- `docs/SPIKE.md` — the spike on St. Albert parcels" in brief
    assert "… …" not in brief
    assert "word … Rejected: the short one." in brief


def test_empty_data_issues_is_not_reported_as_none(tmp_path):
    """An instance may replace the template's DATA_ISSUES table; the brief must
    say it found no rows, never that there are no defects."""
    brief = make_brief.build(_fixture(tmp_path))
    assert "no rows in the six-column table" in brief
    assert "none recorded" not in brief.split("## Known upstream data defects")[1].split("##")[0]


def test_check_goes_red_when_a_source_changes(tmp_path):
    """Falsification for the staleness guard: write the brief, edit a source,
    and `--check` must fail; rewrite, and it must pass again."""
    root = _fixture(tmp_path)
    args = ["--root", str(root)]
    assert make_brief.main(args + ["--check"]) == make_brief.EXIT_FAIL  # missing
    assert make_brief.main(args + ["--write"]) == make_brief.EXIT_OK
    assert make_brief.main(args + ["--check"]) == make_brief.EXIT_OK
    decisions = root / "docs" / "DECISIONS.md"
    decisions.write_text(decisions.read_text() + "| 2026-09-03 | **Newer rule.** | `docs/X.md` |\n")
    assert make_brief.main(args + ["--check"]) == make_brief.EXIT_FAIL
    assert make_brief.main(args + ["--write"]) == make_brief.EXIT_OK
    assert make_brief.main(args + ["--check"]) == make_brief.EXIT_OK
