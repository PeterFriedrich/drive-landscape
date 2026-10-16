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

## Disk

Projects on one host share one disk. On the owner's free-tier server that is
36 GB. On 2026-10-14 it reached 95%, mostly from build intermediates (tiles,
venvs, downloads) that ended sessions had left in their scratchpads, about
2.2 GB from one project. A scratchpad is not cleaned when its session ends.

- **Intermediates go in one work folder** in the session's scratchpad, never
  scattered, so one `rm -rf` clears them.
- **Before a build that writes more than ~500 MB, check `df -h /`.** If the
  build would leave under ~2 GB free, stop and tell the owner instead of
  filling the disk.
- **When the build finishes, delete its intermediates.** Anything worth keeping
  moves to the repo's git-ignored `data/` or `output/` area, where it is
  visible and owned. Don't leave it in scratch.
- **On the owner's server, scratch untouched for 7 days is deleted** by a daily
  cleanup (`server-ops/monitor/scratch-clean.sh`). If you need it longer, such
  as a build you'll resume next session, put a `KEEP` file in the folder saying
  why, and delete the `KEEP` when done. A `KEEP` older than 30 days raises a
  warning.
- **Venvs are built with uv where it is installed** (`bootstrap.sh` falls back
  to venv + pip where it isn't). On 2026-10-16 the project venvs on the
  owner's server held about 3.4 GB, mostly the same scientific stack repeated.
  uv links each package from one shared cache (`~/.cache/uv`), so numpy,
  pandas and scipy sit on disk once per machine rather than once per project.
  On the server's XFS disk the links are copy-on-write clones, not hard links,
  so `du` still counts every venv in full: measure the saving with `df -h /`.
  Install packages with `uv pip install`, not `.venv/bin/pip`: a uv venv has
  no pip, and a pip install copies files outside the cache.
- **A venv made with pip stays a full copy until it is rebuilt.** A
  `copier update` brings the new `bootstrap.sh`, but an existing `.venv` is
  not rebuilt by it. To rebuild, run `rm -rf .venv && ./bootstrap.sh` in place.
  Don't build it elsewhere and move it in, because a venv's scripts hard-code
  its path. A worktree's symlinked `.venv` points at the path, so it survives.
  If a scheduled job (cron, or a wrapper script it calls) runs
  `.venv/bin/python`, rebuild outside its window.
- ⚠️ **Before deleting a venv, check it against `requirements.txt`.** A
  package installed by hand and never added there is silently gone after the
  rebuild. In the 2026-10-16 rollout, alberta lost pandas this way, and
  tax-viz would have lost pypdf and pip-audit and rolled back about 20 pins.
  This lists what is installed but not named in `requirements.txt`, including
  dependencies, so read it for what the code imports:

  ```bash
  norm() { cut -d= -f1 | tr 'A-Z_.' 'a-z--' | sort -u; }
  comm -23 <(uv pip freeze --python .venv/bin/python | norm) \
           <(grep -oE '^[A-Za-z0-9_.-]+' requirements.txt | norm)
  ```

  Pin anything missing in `requirements.txt` and commit it first. Then
  rebuild. (Without uv: `.venv/bin/python -m pip freeze`.) The merge gate's
  `scripts/check_requirements.py` already fails on an unpinned *import*; this
  diff is for what it can't see: CLI tools such as pip-audit, and packages
  loaded by name at runtime.

## Going forward

When you learn a new efficiency lesson (a file that shouldn't be read raw, a
directory that's ballooning, a read pattern that wasted tokens), record it here.
