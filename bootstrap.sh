#!/usr/bin/env bash
# One-time setup after `copier copy` (docs/COPIER.md). Idempotent.
set -euo pipefail
cd "$(dirname "$0")"

# Hooks are not cloned. Without this the pre-push guard is OFF.
git config core.hooksPath .githooks
echo "core.hooksPath -> .githooks"

# The guards use `str | None` (3.10+) and the CI pin is recent; a bare
# `python3` can be 3.6 (Oracle Linux 8), where `pip install -r` fails outright.
if [ ! -x .venv/bin/python ]; then
  py=""
  for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3.10; do
    [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { py="$c"; break; }
  done
  [ -n "$py" ] || { echo "no python >= 3.10 on PATH (set PYTHON=/path/to/python3.x)"; exit 1; }
  # uv links packages from one shared cache, so a stack shared by several
  # projects sits on disk once (docs/TOKEN_EFFICIENCY.md §Disk). The pinned
  # interpreter stops uv downloading a Python of its own.
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python "$py" .venv
  else
    "$py" -m venv .venv
  fi
fi
echo "venv: $(.venv/bin/python --version)"
if command -v uv >/dev/null 2>&1; then
  uv pip install -q --python .venv/bin/python -r requirements.txt
else
  # A venv uv made has no pip; give it one rather than fail on a machine without uv.
  .venv/bin/python -m pip --version >/dev/null 2>&1 || .venv/bin/python -m ensurepip >/dev/null
  .venv/bin/python -m pip install -q -r requirements.txt
fi
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/check_doc_citations.py
.venv/bin/python scripts/check_decisions_log.py

# Claude Code auto-memory is per project path. The feedback-type memories from
# a sibling project (how the owner wants work done) are the most portable
# lessons there are; offer to seed them.
src="${1:-}"
if [ -n "$src" ]; then
  slug="$(pwd | tr '/' '-')"
  dst="$HOME/.claude/projects/$slug/memory"
  mkdir -p "$dst"
  n=0
  for f in "$src"/*.md; do
    [ "$(basename "$f")" = "MEMORY.md" ] && continue
    grep -q '^  type: feedback' "$f" || continue
    cp -n "$f" "$dst/" && n=$((n + 1))
  done
  # Rebuild the index from frontmatter so it matches what was copied.
  {
    echo "# Memory Index"
    echo
    for f in "$dst"/*.md; do
      [ "$(basename "$f")" = "MEMORY.md" ] && continue
      name="$(sed -n 's/^name: //p' "$f" | head -1)"
      desc="$(sed -n 's/^description: //p' "$f" | head -1 | sed 's/^"\(.*\)"$/\1/')"
      echo "- [$name]($(basename "$f")) — $desc"
    done
  } > "$dst/MEMORY.md"
  echo "seeded $n feedback memories into $dst"
else
  echo "To seed feedback memories from a sibling project:"
  echo "  ./bootstrap.sh ~/.claude/projects/<-path-of-sibling>/memory"
fi
