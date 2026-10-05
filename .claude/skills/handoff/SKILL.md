---
name: handoff
description: Write a session state document so work can resume in a fresh session without context loss.
---

# Role
You are a Senior Technical Lead. Create a comprehensive "Session State & Handoff" document from our current conversation.

# Objective
Write a Markdown file to ./session-summary/ (append to today's file if one exists) detailed enough that a fresh Claude session could read ONLY this file and immediately resume.

# Guidelines
- Be specific: not "fixed the bug" but "fixed NullReference in auth.ts by initializing user object"
- Include exact file paths, commands, variable names
- Capture gotchas and environment quirks
- Next steps must be executable tasks
- If a section has nothing, say so — a gap is better than plausible-sounding fiction

# Recording the model + effort (§0)
Open every handoff with the model and effort level that produced the work. It
tells the next session (and the owner) how hard to re-check what it is reading —
a weaker or lower-effort session's output warrants a closer review pass, and
that judgement is impossible to make after the fact if nobody wrote it down.

How to fill it in, in order of reliability:
- **Effort — verifiable.** `echo "$CLAUDE_EFFORT"` (e.g. `high`). Run it; do
  not recall it. If the variable is empty, write "not exposed", not a guess.
- **Model — from the session's own context**, e.g. "Sonnet 5
  (`claude-sonnet-5`)". There is no on-disk record to check this against.
- ⚠️ **A mid-session `/model` switch may not be reflected in the running
  context.** If the model was changed part-way (or you are unsure), say so and
  attribute per phase — "built under Sonnet 5, reviewed under Opus 5" — rather
  than printing one confident name over work two different models did. This
  is not hypothetical: it happened 2026-08-06, and the review that followed
  the switch found a live regression the building session had shipped.
- If work spanned models, note **which parts** each did. That is the whole
  point of the section.

# Claude web sync check
Only if `docs/BRIEF.md` exists (the project syncs into a claude.ai Project —
`docs/CLAUDE_WEB.md`). The Project's copy refreshes only when the owner presses
Sync, and nothing on the web side can notice it is stale. Run:

```bash
last=$(git log -1 --format=%H -- session-summary/)
git fetch -q origin && git log --oneline ${last:+$last..}origin/master -- docs/BRIEF.md 'docs/SPEC_*.md' docs/ARCHITECTURE.md data/DATA.md
```

Any output → Next Steps item 1 is "**Press Sync in the claude.ai Project**
(changed on master: <files>)". Also if this session's still-open PR changes
one: "after merging #N". No output → say nothing about it.

# Output Format

## 0. Session Metadata
- **Model:** <e.g. Opus 5 (`claude-opus-5`)> — note per-phase if it changed mid-session
- **Effort:** <value of `$CLAUDE_EFFORT`, checked not recalled>
- **Date / session #:** <e.g. 2026-08-06, S96>

## 1. Goal
- High-level goal of the project
- What this session specifically tried to achieve

## 2. Current State
### ✅ Completed
### ⚠️ In Progress (where exactly did we stop?)
### ❌ Blocking Issues (paste relevant errors/logs)

## 3. Technical Learnings
- Discoveries made this session
- Important file locations

## 4. Next Steps (prioritized)
1. Exact first action for next session
2. ...

## 5. Restoration Procedure
- How to get the environment running again
