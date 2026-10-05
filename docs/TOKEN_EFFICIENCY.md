# Token Efficiency

Practices for keeping context/token usage low as the codebase grows. This is a
living doc — add to it whenever a new "don't read that raw" or "that directory is
growing" lesson comes up. Rough tokens ≈ bytes ÷ 4.

⚠️ **The lever is what the standing instructions require, not how files are
split.** Nobody reads the corpus; a task touches a handful of files. What every
session pays unconditionally is the *loaded path* — `CLAUDE.md` + `TODO.md` + the
latest handoff + the memory index. Measure that (`tools/retrieval_report.py`
prints it) before optimizing anything else.

## Rules

1. **Never `Read` raw data files.** A single GeoJSON can be millions of tokens —
   one raw read blows the entire context window. Always inspect via a small
   python snippet that prints a *summary* (shape, columns, `head`, value counts,
   a few rows) — never the raw bytes. Large generated JSON under `web/` is the
   same hazard in a different extension.

2. **Read only the latest session summary.** Start work from the newest handoff.
   Do NOT bulk-read or glob-grep across the whole directory. Keep the **3 most
   recent** handoffs at the top level; older ones live in
   `session-summary/archive/` so a `session-summary/*.md` glob doesn't reach
   them. `tests/test_loaded_path.py` enforces this.

3. **Prefer targeted reads over whole-file reads for anything large.** Use
   `Read` with `offset`/`limit`, or `grep` to locate the lines first, when a
   file is more than a couple hundred lines.

4. **Keep modules small and single-purpose.** One processing step per file,
   ≤~250 lines. If a module crosses ~400 lines, that's the signal to split.

5. **⚠️ MANY SMALL READS ARE THE EXPENSIVE PATTERN, not one big one.** Every
   tool result persists and is re-sent on every later turn, so 21 reads of
   30–60 lines cost far more than 4 large ones covering the same ground — plus
   the overlap is paid twice. **Decide what you need up front, then read it in
   a few large slices.** Batch independent reads into one turn.

6. **Never let raw markup, SVG or JSON blobs into the transcript.** Pipe
   through `cut`/`sed` or return only the fields being asserted.

7. **Batch slow runs — the prompt cache has a short TTL.** A test or browser
   invocation that runs longer than the TTL means the next turn re-reads the
   whole accumulated context uncached. Run slow things together, or in the
   background while doing reads.

8. **Idle wakeups cost as much as real turns.** A scheduled check-in re-sends
   the whole conversation, and wakes an hour apart mostly miss the cache. A
   PR that waited overnight for the owner cost about 8 turns that did nothing.
   Follow PRs by subscribing to their events, never on a timer:
   `.claude/skills/steward/SKILL.md`.

## Files to watch

- `session-summary/` — grows every `/handoff`; the archive policy keeps it bounded.
- `TODO.md` — read first every session, so closed work must leave it
  (`tools/todo_archive.py`).
- `docs/DECISIONS.md` — append-only; rows grow. Not on the loaded path, but
  grep it rather than reading it whole.
- <add the project's own large files here as they appear>

## Going forward

When you learn a new efficiency lesson (a file that shouldn't be read raw, a
directory that's ballooning, a read pattern that wasted tokens), record it here.
