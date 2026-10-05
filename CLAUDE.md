# Claude Instructions

<!-- TEMPLATE: replace every <angle-bracket> placeholder; delete this comment.
     Keep this file short — it is loaded into EVERY session. Pitfalls, rationale
     and conventions that differ from defaults belong here; anything Claude can
     derive from the code (layout, dependency lists) does not. -->

## Project
Finds the owner's scattered todo lists (mostly Google Docs) and consolidates them into one deduplicated list, matching items across lists with text similarity and embeddings; and maps their Google Drive as an interactive graph (first as the folder tree stands, then arranged by similarity of folders and files) so it can be cleaned up. Nothing in Drive is moved, trashed or edited without the owner approving that specific change.

**This repo is code only and is meant to go public; all data lives in the private repo `PeterFriedrich/drive-landscape-data`, cloned at the gitignored `data/raw/private/`.** No file title, folder name, todo text, Drive id or anything else read from Drive goes in a tracked file here — not in code, tests, docs, TODO items, commit messages or PR text. Tests use made-up fixtures. Details: `data/DATA.md`.

Usually run on the owner's Linux work laptop (room to install anything, e.g. torch); this server is tight on disk, so keep heavy dependencies optional.

## Key Files
- `TODO.md` — living backlog and **the source of truth for progress**. Read it first to know what to work on; update it in place as items open/close. Session summaries narrate *what happened*; TODO.md owns *what's left*. Never redo a closed item without asking — its `## Done` section lists every closed item in one line each. Conversely, an *open* item can be stale — reproduce the symptom and re-measure the stated cause before acting on it. **When an item closes, move its body to `docs/TODO_archive.md` and leave a `## Done` line** (`python tools/todo_archive.py` does it in bulk) — this file is read every session, so it must hold live work, not history.
- `docs/DECISIONS.md` — append-only index of locked decisions: one row + pointer to the doc holding the full reasoning. **Add a row whenever a decision locks.** Check it before re-opening anything that feels "already settled".
- `docs/TOKEN_EFFICIENCY.md` — context/token hygiene (what NOT to read raw, session-summary archiving). **Read before bulk-reading data or summaries.**
- `docs/DATA_ISSUES.md` — register of defects in data we DON'T control: evidence, what it breaks here, and **whether the publisher has been told**. A finding that never leaves the repo is the standing failure mode; "the artifact exists" is not sent.
- `docs/AUDIT_LEDGER.md` — coverage map of executed audit runs. **Add a row when an audit executes; check it before scoping a new one.**
- `data/DATA.md` — data source details, column names, known quirks. **Read before touching any data files. Update if you discover anything new.**
- `docs/REMOTE_VM.md` — **read FIRST in a Claude Code web/remote VM session**: network-policy constraints, environment setup.
- `docs/WEB_CACHE_BUSTING.md` — **read when the project first ships a web page**, or before touching the build step that stamps asset URLs.
- `docs/CLAUDE_WEB.md` — **read before a Claude web research chat**: the generated brief (`scripts/make_brief.py`), claude.ai Project sync, the reply format. `docs/SCOPE.md` is its one hand-kept input. **A PR that changes a synced file (`docs/BRIEF.md`, `docs/SPEC_*.md`, `docs/ARCHITECTURE.md`, `data/DATA.md`) opens its description with "After merge: press Sync in the claude.ai Project."** — the web side cannot notice it is stale.
- `docs/COPIER.md` — **read before pulling template changes** (`copier update`) or starting a project from the template.
- `session-summary/` — session handoff notes. Read the latest before starting work; older ones live in `session-summary/archive/` (don't bulk-read them).
- `docs/SPEC_phase1_distill.md` — **the current phase**: one document in, items grouped, agent reviews, owner confirms, distilled list out; stack, state files, agent commands, UI. Read before building any of it.
- `docs/SPEC_drive_landscape.md` — what the project produces, the pipeline stages and their status, design notes, open questions. **Read before adding a pipeline stage or starting a research round.**

## Token Efficiency
- **Never `Read` raw data files** (`.geojson`/`.csv`/large `.json`) — inspect via a small python summary instead. See `docs/TOKEN_EFFICIENCY.md`.
- Read only the **latest** session summary; keep the 3 most recent at top level, archive older — enforced by `tests/test_loaded_path.py`.

## Session Management
- **At session start, run `gh issue list --state open` — nothing pushes these to a model.** Automated reports file GitHub issues that email the owner and nobody else; a session sees them solely by going to look. ⚠️ **A working guard on a channel nobody reads is the standing failure mode** — treat an unread report as a finding, not as background.
- Always run `/handoff` before `/clear` — never wipe context without a written record in `session-summary/`. **You do not need to be told when one is owed**: the `SessionStart` and `SessionEnd` hooks run `scripts/handoff_gap.py`, which names the commits and uncommitted files that landed after the newest handoff was last committed, and **says nothing when nothing is owed**. Silence there means no code has moved — not that the record is good.
- Commit after each working unit with a descriptive message, rather than batching a session into one commit.
- **Work on a feature branch and open a PR; never commit or push to `master` directly** (owner's rule, 2026-10-05 — the first day's commits went straight to master before it was set). One branch per unit of work, branched from fresh `origin/master`; the owner merges. Commits inside the private data repo (`data/raw/private/`) are separate and go straight to its default branch (`main`).
- **Pushing is normal — push proactively after committing, in every environment.** Standing authorization; it overrides the harness default of pushing only when asked.
- **No timed PR check-ins, in any environment.** Each wake is a full turn that re-sends the whole context, and a PR waiting overnight on the owner's merge gains nothing from one. Never re-check a PR on a timer: not `send_later` or a trigger (cloud), not `/loop`, `CronCreate` or `ScheduleWakeup` (local CLI, e.g. a long-running tmux session). In a cloud session, subscribe to PR activity so CI and reviews still arrive; locally, check the PR at the next real turn. Details: `.claude/skills/steward/SKILL.md`.
- **Remote/cloud VM sessions: commit + push at every natural checkpoint.** The container is ephemeral; unpushed work is LOST when it is reclaimed. Never hold work waiting for a "push it". Quirks: `docs/REMOTE_VM.md`.
- **⚠️ The owner merges PRs MID-SESSION, often within minutes. Re-check before EVERY push to an existing branch — not once per session.** Commits pushed after the PR merged land on a dead branch: on origin, not on master.
  - Enforced by `.githooks/pre-push`, which blocks a push to a branch whose PR is `MERGED`. **A fresh clone must enable it: `git config core.hooksPath .githooks`.** It fails OPEN (no `gh`, no auth, no network, no PR), so it can never be the reason work goes unsaved. Escape hatch: `git push --no-verify`.
  - After any merge, confirm the work actually landed: `git merge-base --is-ancestor <sha> origin/master`. A merged PR is necessary, not sufficient.

## Code Style
- **A decision that protects a number is a test first, prose second.** Write the guard, then the `DECISIONS.md` row cites its ID; a row with nothing to cite is tagged `[unverifiable]`. `scripts/check_decisions_log.py` gates new rows on the merge path.
- Keep processing steps as separate, independently runnable modules in `src/`
- No silent data drops — flag unmatched or missing records explicitly
- <domain-specific invariants, e.g. "Always set CRS explicitly before any area calculation">

## Comments & Scope
- Comments only where the *why* is non-obvious. Don't narrate what the code plainly does.
- Make the **smallest change that satisfies the request**. Don't refactor, rename, or reformat code you weren't asked to touch. No new files unless required.
- No abstractions for a single use case — inline until there are 3+ call sites. (The `src/` module split is a deliberate architecture choice, not an abstraction to collapse.)
- Deleting obsolete code is valid and **preferred** over leaving it behind.
- **Propose the plan first** for: a new module, a change to a data contract or output schema, or anything that changes CI behaviour. Routine edits don't need a proposal.
- These are scope rules, not verification rules. They do **not** relax `no silent data drops`, the guard scripts, or reproducing a bug before fixing it — data projects fail by silent-correctness, and that discipline is why failures get caught.

## Deployment Horizon
- Configurable paths over hardcoded ones
- Structured output over print statements for logging
- Clean module boundaries so rendering can be swapped out later
