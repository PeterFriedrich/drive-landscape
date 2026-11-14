# Audit brief: private data in the public repo

A read-cold instrument for one question: **has anything read from Drive reached
a public surface of `PeterFriedrich/drive-landscape`?** Written 2026-11-14 for
a Fable run; re-runnable. It holds the method and the questions, never the
findings.

## Why this target

The repo is public and code-only (`CLAUDE.md` "Project"). The guard,
`scripts/check_no_private_data.py` (pre-commit and merge gate), blocks data
paths, credential files, oversized files and Drive/Docs links. Its own
docstring says what it cannot do: recognise a file name, a theme name or todo
text typed as prose. That half of the rule rests on the author, and the
authors are agent sessions that had just read the owner's real list while
writing commit messages, PR bodies, handoffs and fixtures. Nothing has checked
it since the repo went public.

## ⚠️ Where the findings go

**Findings quote private text, so they never go in this repo.** Write them to
the private repo: `data/raw/private/audits/<YYYY-MM-DD>_privacy_leak.md`,
committed on its `main`. In this repo, the only output is the
`docs/AUDIT_LEDGER.md` row: counts per surface and verdicts, with **no quoted
text, no titles, no commit-message excerpts**. Point to the private file by
path. Run the ledger row through the same corpus match (below) before
committing it.

**The audit reports. It does not fix.** Every fix to a public surface (history
rewrite, force push, editing a PR body, deleting a branch) is outward-facing
and hard to reverse. List the fixes; the owner approves each one.

## Grounding order

1. `CLAUDE.md` "Project", `data/DATA.md` "Where the data lives" and
   "Todo lists": what counts as private.
2. `scripts/check_no_private_data.py` and `tests/test_no_private_data.py`:
   what is already caught, so you don't re-find it.
3. `docs/DECISIONS.md`: read the **full body** of any row about privacy, ids
   or the private repo. Some exceptions are settled (for example, the S11
   handoff records why the live doc's id may sit in the *private* repo).

## Step 1: build the corpus of private strings

From `data/raw/private/` (everything there is private; on the server it may
hold only `todo/`, while the laptop clone may hold more, such as
`inventory/` and `live/`, so record which machine and which commit you used):

- every item's text, from `todo/*/items.jsonl` and `list.md`, plus edited
  lines and split parts from each `work/` state;
- every theme and group name;
- every Drive file/folder name and id from any inventory or `doc.json`;
- source document titles (`extract_summary.json`, manifests, PDF names);
- the private repo's own **history** (`git -C data/raw/private log -p`):
  text that was later edited away still counts.

Normalise (case, whitespace, punctuation, list markers). Match three ways:
- **ids and exact strings**, for ids, titles, names;
- **word n-grams** (start at 4; lower it for short items and log the
  false-positive rate) for todo text;
- **distinctive single tokens**: proper nouns, unusual words, numbers that
  occur in the corpus and nowhere in ordinary English or code. Expect noise
  here and triage it by hand.

Record the corpus size and the match thresholds in the findings.

## Step 2: the public surfaces (one verdict each)

| # | Surface | How to read it |
|---|---------|----------------|
| S1 | Tracked files at HEAD | `git ls-files` |
| S2 | **Every blob in history**, including deleted files and files later rewritten | `git rev-list --all --objects`, `git log -p --all` |
| S3 | Commit messages, author lines | `git log --all --format=%B` |
| S4 | Branch and tag names on origin | `git ls-remote origin` |
| S5 | PR titles, bodies, review comments, issue comments | `gh pr list --state all`, `gh api` for comments and reviews (PR bodies can be edited, so this reads the current text; GitHub keeps body edit history, so check `userContentEdits` too) |
| S6 | Issues, open and closed, with comments | `gh issue list --state all` |
| S7 | Session summaries and archive, `docs/BRIEF.md`, `TODO.md`, `docs/TODO_archive.md` | in S1/S2, but **read them by hand**, see Step 3 |
| S8 | Test fixtures | in S1/S2; confirm each fixture is invented, not trimmed from real data |

Out of scope (not public): untracked local files, `~/.claude` auto-memory,
the claude.ai Project (it only syncs tracked files, already covered by S1).
Say so in the findings rather than staying silent.

## Step 3: what string matching misses

A handoff can leak without quoting: "the owner's item about <named person>'s
<event>", a paraphrased theme, a count that identifies something. String
matching cannot find that. **Read every session summary, every PR body and
every commit message longer than one line in full**, with the corpus to hand,
and ask: could someone who reads this learn something specific about the
owner's life, work or files?

Severity tiers:
- **High**: verbatim or near-verbatim private text, a title, a name, an id.
- **Medium**: a paraphrase specific enough to identify the item or file.
- **Low**: aggregate shape only (counts, "a theme about work"). Usually
  acceptable; list it so the owner can judge.

Item numbers (`560.2`) and theme ids are positions in a list, not content.
Treat them as not private unless next to text that is.

## Step 4: the guard

Answer as PASS / FAIL / WARN:
- Does any finding fall in a class the guard already claims to catch? If so,
  the guard has a bug. Reproduce it with a made-up fixture.
- Would a corpus match at commit time be sound? The pre-commit hook runs where
  `data/raw/private/` usually exists. Sketch how it would work: what to match,
  how it fails when the private clone is missing, how it stays fast, and
  how it avoids writing the corpus anywhere tracked. Also cover commit-message
  and PR-body checks (`commit-msg` hook; a `gh` wrapper or a pre-push check).
  **Propose it, don't build it**: a new guard changes CI behaviour, and
  `CLAUDE.md` asks for a plan first.

## Verdict shape

Per surface S1–S8 and for the guard:

```
## Audit: S<n> <surface>
**Verdict:** PASS / FAIL / WARN
**Finding:** count by severity; the location of each (sha, path:line, PR #); the matched text, in the PRIVATE findings file only.
**Fix:** the concrete change, with its blast radius (history rewrite vs. edit vs. none).
```

For any FAIL in S2–S6, also note: how long it has been public, whether forks
or clones exist (`gh api repos/{owner}/{repo}/forks`), and that rewriting history
does not remove what GitHub caches (PR diffs, old commits reachable by sha).
Removing those is a GitHub support request.

The findings end with **What this run got wrong**, which may not be empty.
The highest-risk claim here is "S<n> is clean". Back every PASS with the
corpus size, thresholds and number of objects read, and check one known
true positive (plant a corpus string in a scratch copy of the repo) to show
the matcher would have found it.

## Close the loop

- `docs/AUDIT_LEDGER.md` row (no private text). Move this brief from
  "Queued" to the executed table.
- `TODO.md`: one item per owner-approved fix, plus the guard proposal.
- Ship the ledger and TODO change as a PR here. Commit the findings in the
  private repo.
