# AUDIT LEDGER — what has been audited, when, and what came back

One row per **executed audit run**. This is the coverage map the audit docs
don't give individually: briefs are reusable *instruments*, findings docs record
*one run's output*, and the `project-audit` skill deliberately picks ONE target
per session — so nothing else says what has and hasn't been looked at. This does.

Rules: add a row when an audit **executes** (not when a brief is written); every
row carries a **pointer to the findings doc**; verdicts are **point-in-time** — a
row says the target was audited *as of that date*, not that it's still clean
after later changes. Not part of any session's mandatory reading — open it to
scope an audit or to check what has already been covered. Audits are framed
top-down, fundamental decisions first.

## Executed audits

| Date | Target / scope | Instrument | Output | Verdict (one line) | Outstanding |
|------|----------------|------------|--------|--------------------|-------------|
| 2026-11-15 | Private data on the public repo's surfaces, as of `59405e7`: 79 files at HEAD (S1), 290 blobs across 113 commits on 49 branches and 48 PR refs (S2), 113 commit messages and author lines (S3), 49 branch names and 0 tags (S4), 48 PRs with 6 earlier body versions and 1 earlier title, 0 comments or reviews (S5), 0 issues (S6), 11 handoffs and every version of `TODO.md`, the archive, `docs/SCOPE.md` and `docs/BRIEF.md` read by hand (S7), 43 test blobs (S8), and the guard. Corpus: the private repo at `d017b4c` on the server, which holds one todo list and no Drive inventory or live-inbox data. | `docs/AUDIT_privacy_leak.md` (Fable run; string, n-gram, token and id matching, then reading by hand; a planted true positive was found in a deleted file, a commit message and a branch name) | Private repo: `data/raw/private/audits/2026-11-15_privacy_leak.md` (`c8ad3f4`) | S1–S8 PASS: 0 High, 0 Medium; Low is aggregate shape only (counts, source format, workflow notes). Guard WARN: no bug in what it claims to catch, but prose, bare ids, commit messages, branch names and PR text are checked by nobody. | Owner: five decisions listed in the findings, none of them a change to a public surface for Drive data. A corpus-match guard is proposed, not built. Re-run once the private repo holds inventory or live-inbox data: Drive names and ids were covered by generic id scans only, and the three titles removed on 2026-10-05 could not be recovered to search for. `TODO.md`. |

## Queued — briefed, not yet run

- (none)

## Never audited (candidates, roughly ranked)

- <the data join / the denominator / the published headline number …>
