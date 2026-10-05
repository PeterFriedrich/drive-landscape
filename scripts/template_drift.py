"""Has the template moved since this project last took its changes?

A project made with copier records the template commit it was last brought up
to (`_commit` in `.copier-answers.yml`). Nothing else tells it when the
template improves, and "remember to run `copier update`" is a rule with no
reader: `alberta-regional-viz` missed a week of template fixes that way. So a
SessionStart hook runs this, and when template files that reach a project have
changed, the session is told which ones — **to evaluate, not to apply blindly**
(`docs/COPIER.md` §"When the session-start notice appears").

Changes to the template's own state (its backlog, handoffs, findings) never
reach a project, so they are ignored: a notice after every template handoff
would be one people learn to skim. `IGNORED` mirrors `copier.yml`, and the
template's `tests/test_copier.py` fails if the two disagree.

⚠️ **Fails silent, always**, like `handoff_gap.py`: no answers file (the
template itself), a local `_src_path`, no network, a rate limit, an unknown
commit — every one exits 0 saying nothing. Silence means "no notice", not
"verified current". It never blocks a session.

Cost: one `git ls-remote` per session start. The GitHub compare API is called
only when the template's HEAD differs from `_commit` (via `gh` when available,
else unauthenticated — 60 requests/hour, plenty for a public template).

Usage:
    python scripts/template_drift.py                  # plain text, or nothing
    python scripts/template_drift.py --session-start  # SessionStart hook shape
"""

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ".copier-answers.yml"
TIMEOUT = 8
MAX_LISTED = 12

# Template paths whose changes never reach an existing project. Keep in step
# with copier.yml: its _exclude, its _skip_if_exists (written once, then the
# project's), and each plain file shadowed by a `.jinja` sibling.
# tests/test_copier.py pins the match.
IGNORED = [
    "copier.yml", "tests/test_copier.py",
    "session-summary/*.md", "docs/FINDINGS_*.md", "docs/BRIEF.md",
    "README.md", "docs/SCOPE.md", "data/DATA.md",
    "TODO.md", "docs/DECISIONS.md", "docs/TODO_archive.md",
]


def read_answers(root: Path) -> dict[str, str]:
    """The two keys we need, without a YAML dependency."""
    p = root / ANSWERS
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(_commit|_src_path):\s*['\"]?([^'\"#\s]+)", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def github_repo(src: str) -> str | None:
    """`owner/repo` for a GitHub source, None for anything else (a local path)."""
    m = re.match(r"^(?:gh:|https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?$", src)
    return m.group(1) if m else None


def base_ref(commit: str) -> str:
    """copier records `git describe` output: a sha, a tag, or `<ver>+g<sha>` /
    `<tag>-N-g<sha>`. The sha, where there is one, is what compare needs."""
    m = re.search(r"(?:\+|-g)g?([0-9a-f]{7,40})$", commit)
    return m.group(1) if m else commit


def reaches_project(path: str) -> bool:
    return not any(fnmatch.fnmatch(path, pat) for pat in IGNORED)


def remote_head(repo: str) -> str | None:
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}", "HEAD"],
                         capture_output=True, text=True, timeout=TIMEOUT)
    return out.stdout.split()[0] if out.returncode == 0 and out.stdout.strip() else None


def compare(repo: str, base: str, head: str) -> dict:
    api = f"repos/{repo}/compare/{base}...{head}"
    if shutil.which("gh"):
        out = subprocess.run(["gh", "api", api], capture_output=True, text=True, timeout=TIMEOUT)
        if out.returncode == 0:
            return json.loads(out.stdout)
    req = urllib.request.Request(f"https://api.github.com/{api}",
                                 headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def drift(root: Path = ROOT) -> dict | None:
    """{repo, base, head, files} when template files that reach this project
    changed since `_commit`; None otherwise."""
    ans = read_answers(root)
    repo = github_repo(ans.get("_src_path", ""))
    if not repo or "_commit" not in ans:
        return None
    base = base_ref(ans["_commit"])
    head = remote_head(repo)
    if not head or head.startswith(base):
        return None
    data = compare(repo, base, head)
    if data.get("status") not in ("ahead", "diverged"):
        return None
    files = sorted(f["filename"] for f in data.get("files", []) if reaches_project(f["filename"]))
    if not files:
        return None
    return {"repo": repo, "base": base, "head": head[:7], "files": files}


def message(d: dict) -> str:
    listed = ", ".join(f"`{f}`" for f in d["files"][:MAX_LISTED])
    more = f" and {len(d['files']) - MAX_LISTED} more" if len(d["files"]) > MAX_LISTED else ""
    return (
        f"Template update available: {len(d['files'])} file(s) that reach this project changed "
        f"in {d['repo']} since {d['base']}: {listed}{more}. "
        f"Diff: https://github.com/{d['repo']}/compare/{d['base']}...{d['head']} . "
        f"Evaluate before taking it — `docs/COPIER.md` §\"When the session-start notice appears\"; "
        f"tell the owner, don't apply it unasked."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-start", action="store_true",
                    help="SessionStart hook shape (additionalContext + systemMessage)")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    try:
        d = drift(args.root)
    except Exception:  # noqa: BLE001 — a hook must never raise
        return 0
    if d is None:
        return 0
    text = message(d)
    if args.session_start:
        print(json.dumps({
            "systemMessage": text,
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
        }))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
