# Remote VM sessions (Claude Code on the web) — read FIRST in one of these

A remote session is recognizable by: repo cloned at `/home/user/<repo>`, no
conda, empty `data/raw/`, and a session-specific branch name like
`claude/<something>`.

## The rules that differ from local sessions

- **Push proactively at every checkpoint** — see CLAUDE.md "Session
  Management". The container is ephemeral; unpushed work is lost when it
  idles out. Never wait for a "push it".
- **Work on the session's designated branch** (the harness names it). The
  handoff commit goes on the branch too; the merge carries it over.
- **No PR unless asked.**

## Network policy — the big constraint

The VM's outbound HTTPS goes through an allowlist proxy that ALLOWS
registry.npmjs.org, pypi.org and GitHub, and **BLOCKS most of the web** —
including, until added, the open-data portals this project reads. That means
no raw data downloads and no CDN scripts unless the policy is changed.

- Diagnose: `curl -sS "$HTTPS_PROXY/__agentproxy/status"` — a
  `connect_rejected` / "gateway answered 403 to CONNECT" entry for a host
  means policy denial, not a transient failure. Don't retry; don't disable
  TLS or unset HTTPS_PROXY.
- **The fix is the owner's, not the session's**: claude.ai/code → this
  environment's settings → network access → add the data hosts to the allowed
  domains. Applies to NEW sessions.
- Until then: build with synthetic tests (the standard pattern anyway), guard
  frontends on missing columns, and let a CI workflow (GitHub runners, open
  network) populate real data after merge.

## Environment setup (fresh container)

```bash
pip install -r requirements-ci.txt
git config core.hooksPath .githooks  # ⚠️ HOOKS ARE NOT CLONED — see below
python3 -m pytest tests/ -q          # all-synthetic, no data needed
```

⚠️ **`core.hooksPath` matters MOST here.** `.githooks/pre-push` blocks a push to
a branch whose PR is already merged. Git does not clone hooks, so in a fresh
container it is **OFF until you set it**, and this is exactly the environment
where a stranded commit is unrecoverable. The hook **fails open**, so it can
never be the reason work goes unsaved. It is a backstop, not a substitute for
`git merge-base --is-ancestor <sha> origin/master` after any merge.
