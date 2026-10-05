# COPIER — how template changes reach this project

**Read when:** starting a new project from the template, pulling template
changes into a project, or connecting a project that was made before copier.

The template (`PeterFriedrich/cc-data-project-template`) is canonical for the
workflow apparatus. [copier](https://copier.readthedocs.io) records in
`.copier-answers.yml` which template commit a project was last brought up to;
`copier update` then applies only what changed in the template since, as a
three-way merge. A project's own edits survive (renaming "the owner", adding a
Key Files line); a line changed on both sides comes back as a conflict, never a
silent overwrite.

What a project never receives (`copier.yml`): the template's own handoffs,
findings docs and brief. Its ledgers (`TODO.md`, `docs/DECISIONS.md`,
`docs/TODO_archive.md`) arrive as empty skeletons. `README.md`, `docs/SCOPE.md`
and `data/DATA.md` are written once and never touched by an update.

## New project

```bash
pipx install copier   # once per machine; or: python3 -m pip install --user copier (Python >= 3.9)
gh repo create PeterFriedrich/<new-project> --public --clone   # or --private
cd <new-project>
copier copy --trust gh:PeterFriedrich/cc-data-project-template .
./bootstrap.sh
git add -A && git commit -m "Start from cc-data-project-template"
```

Use this instead of GitHub's "Use this template": that copies the template
repo's own backlog, decisions and handoffs, and records nothing to update from.

## Pull template changes

On a clean branch:

```bash
copier update --trust --defaults
git status          # conflicts are marked in-file: <<<<<<< before updating
```

Resolve conflicts in favour of the project's own content unless the template
change is the point; run the tests; commit with the new `_commit` in the
message; open a PR. `--trust` lets the template run tasks and extensions; it
has none today, so the flag only matters once it does — and it is the owner's
own repo.

⚠️ **The template is deliberately untagged.** Copier updates to the newest
*tag* when any exist, and to the default branch's HEAD when none do. A tag
would turn every template change that forgot a new tag into one that silently
never arrives. Leave it untagged; copier's "No git tags found in template;
using HEAD as ref" warning is expected (`copier/_vcs.py` `get_latest_tag`).

## When the session-start notice appears

`scripts/template_drift.py` runs at every session start (`.claude/settings.json`)
and says "Template update available: N file(s) …" when template files that
reach this project changed since `_commit`. It is silent when the project is
current, and silent when it can't check (no network, local `_src_path`) — so
silence is not proof of being current.

The notice is information, not an instruction. **Template updates are
evaluated, not applied blindly:**

1. Tell the owner; don't run the update unasked or mid-way through other work.
2. Read the compare link in the notice. For each change, decide: take it,
   adapt it, or decline it — the template is generic, this project may have
   a reason to differ.
3. On a clean branch, run **Pull template changes** above. Before committing,
   revert the hunks you decline (`git checkout -p`). A declined change is not
   re-offered: the next update starts from the new `_commit`, so it stays
   declined. Record a substantive decline in `docs/DECISIONS.md`.
4. Run the tests, commit, open a PR listing what was taken and what declined.

## Connect a project made before copier

A project created from the template by hand has no `.copier-answers.yml`, so
copier doesn't know what it started from. Once:

1. Find the template commit it was made from: compare its first commit's copy
   of template files (`bootstrap.sh`, `CLAUDE.md`, `scripts/*.py`) with the
   template's history (`cmp` against `git show <sha>:<file>`). The earliest
   template commit whose files all match is the one.
2. Write `.copier-answers.yml`:
   ```yaml
   _commit: <that sha>
   _src_path: gh:PeterFriedrich/cc-data-project-template
   ```
   and commit it on its own.
3. Run **Pull template changes** above.

Dry-run 2026-09-29 on a clone of `alberta-regional-viz` (made from `bf5f568`):
the update brought in the steward skill, the cache-busting doc, rule 8 of
`TOKEN_EFFICIENCY.md` and the Claude web brief; left its `TODO.md`,
`DECISIONS.md` and `README.md` alone; kept its "Peter" edits; and conflicted on
one `CLAUDE.md` line both sides had changed.

**Not a copier project:** `edmonton-tax-viz` is where the template was
extracted *from*, and its owned files are deliberately its own (e.g.
`edmonton-audit` in place of `project-audit`). Every update would conflict.
Changes reach it by a session reading the template's PR diff and porting what
fits.
