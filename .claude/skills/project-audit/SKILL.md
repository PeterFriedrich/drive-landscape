---
name: project-audit
description: >
  Focused audit skill for this data-analysis project. Use this whenever the
  user asks to audit, review, check, or QA the pipeline, a metric, or project
  files. Picks ONE audit target per run; grounds in docs/AUDIT_LEDGER.md
  before scoping and adds a ledger row after executing. Triggers on: "audit my
  code", "check the pipeline", "review my project", "what should I look at",
  "is this right", or any QA/review request in the context of this project.
---

# Project Audit Skill

## Purpose

The goal of each audit run is a **single, deep, actionable verdict** on one
target. Do not attempt a broad sweep; pick one focus, go deep, produce clear
verdicts + specific fixes. A focused single-target audit is more useful than a
shallow pass over everything.

## The audit ecosystem (know the pieces before you start)

- **`docs/AUDIT_LEDGER.md`** — the coverage map: one row per *executed* audit
  run, plus a ranked never-audited inventory. **Read it FIRST when scoping;
  add a row when your audit executes.** This skill and the ledger are two
  halves of one loop.
- **Briefs** (`docs/AUDIT_<target>.md`) — reusable read-cold *instruments*. A
  brief is written once and can be re-run; it holds the grounding order and
  the questions, never the findings. **A brief wins over these steps wherever
  the two disagree** — it was written knowing more about its target.
- **Findings** (`docs/FINDINGS_<target>.md`, or handoff sections for smaller
  runs) — one run's *output*. Never duplicated into the ledger.
- **`docs/DECISIONS.md`** — if an audit locks or reopens a decision, append a
  row there too.

## How to run an audit

### Step 1 — Ground before scoping (non-negotiable)

1. Read `docs/AUDIT_LEDGER.md` — all tables.
2. Cross-check the latest session summary. **TODO.md can lag executed work** —
   a backlog item that "smells like an audit" may have already run and only be
   recorded in a handoff. If the ledger and TODO disagree, the ledger +
   summaries win; reconcile TODO in your PR.
3. Ledger verdicts are **point-in-time**: a target audited before a relevant
   change is fair game to re-audit — say so explicitly ("re-run, prior row
   YYYY-MM-DD, delta since: …").

### Step 2 — Pick ONE target

- If the user named a target, use it.
- Otherwise take the top of the ledger's "Never audited" ranked list.
- Tell the user which target you picked and why before going deep.

### Step 3 — Choose the audit family

**(a) Decision audit** (metrics, published claims — the default for anything
user-facing): audit the **fundamental decisions top-down, highest level
first**, not the code.

- Build the target's **decision stack** (L0 "should this be published at all"
  → … → Ln "is the code right") and evaluate in order. **When a level is
  unsound, everything beneath it is moot** — don't polish an edge case under
  a broken unit-of-analysis choice.
- Per-level verdicts: **SOUND / CONDITIONAL** (sound only if a stated caveat
  holds) **/ UNSOUND**, plus the single sharpest argument against the level
  and what evidence would change the verdict.
- Not looking for reassurance: assume the authors believe their own metric;
  the value is the argument they didn't make against themselves. One finding
  that kills a level beats ten that polish one.
- Ground in the repo's written reasoning (SPEC, DECISIONS.md, prior FINDINGS)
  and *challenge* it — don't re-derive it. ⚠️ **Read the BODIES of every
  `DECISIONS.md` row touching your target, and never truncate them** — the
  reasoning lives in the tail, and `grep | cut` hands you a row that matched
  while hiding the sentence that settles your finding. Do this BEFORE writing
  any finding. Runs have published findings the repo had already decided.
- For a substantial new target, **write the brief as a standalone
  `docs/AUDIT_<target>.md`** so the instrument outlives the run.

**(b) Correctness audit** (silent-wrong-numbers risk): verdicts are **PASS /
FAIL / WARN** per target. The checklists are in the appendix below.

### Step 4 — Deliver verdicts

⚠️ **Every findings document MUST end with a `What this run got wrong` section,
and it may not be empty.** This is an *output shape*, not a good intention — a
file missing the heading is visibly missing it. The pattern is consistent:
**the class you are auditing shows up in your own instruments.**

If you genuinely found no error, you have not looked — re-read your sharpest
claim and ask what would have to be true for it to be wrong, then go check
that thing. ⚠️ **A confident NEGATIVE — "nothing reads this", "this can never
fire", "no gate covers this" — is the highest-risk claim shape.** Verify a
negative by finding the reader/trigger, not by failing to find one.

Decision audits: one verdict line per level, sharpest counter-argument,
evidence-that-would-change-it. Correctness audits:

```
## Audit: [Target]
**Verdict:** PASS / FAIL / WARN
**Finding:** [One paragraph. Quote the actual line if there's a bug. Don't hedge.]
**Fix (if needed):** [Concrete change; if PASS, what you confirmed and why.]
```

### Step 5 — Close the loop (this is what makes the run count)

1. **Add a row to `docs/AUDIT_LEDGER.md`**: date, target/scope, instrument,
   output pointer, one-line verdict, outstanding items.
2. Write findings where they belong: a `FINDINGS_*.md` for big runs, the
   session handoff §2 for smaller runs — the ledger row just points.
3. Reconcile `TODO.md` (tick executed items, add follow-ups for
   CONDITIONAL/WARN outcomes) and append to `DECISIONS.md` if a decision
   locked or reopened.
4. Update the ledger's "Never audited" list if your run covered (or
   surfaced) an inventory item.
5. Ship as a PR like any other docs change (`git pull` master before cutting
   the branch — ledger/DECISIONS/TODO tails are append-conflict magnets).

## Escalation

A FAIL on anything that makes published numbers wrong is **blocking** — stop
auditing other targets in the same run; the numbers can't be trusted until it's
fixed. An UNSOUND on a top decision level moots the rest of that stack: report
it and stop descending. WARN/CONDITIONAL/architecture issues: list them, let
the user decide order.

---

## Appendix — correctness checklists (family b)

### Units and reference systems
The most dangerous silent failure: a computation in the wrong unit that
produces plausible numbers with no error (degrees² for area, cents for
dollars, fiscal for calendar year). Every conversion is explicit and asserted
at the boundary. <For spatial work: `.to_crs()` before any `.area`; name the
project's canonical EPSG here.>

### Silent data drops
Unmatched records are flagged, never silently dropped. Check: keys normalized
before joins; explicit unmatched-row check after; counts + examples logged;
before/after record counts visible so drift shows.

### Guards measure data, not metadata
A guard that reads a "last updated" string or a coverage label stays green
while the data underneath moves. Check the numbers themselves — row counts,
max dates, totals.

### Module independence
Each `src/` module runnable standalone: own/argued paths, no top-level state
imports from sibling modules, existence checks on upstream outputs, traceable
raw → joined → calculated → output flow.

### Methodology
Aggregations are the right kind (sum vs mean), exclusions documented and
intentional, denominator source stated.

### DATA.md currency
Column names, row counts, quirks, join match rates, exclusions — all matching
reality. A stale DATA.md means knowledge is leaking between sessions; flag it.
