# TODO — archive of CLOSED items

Closed work moved out of `TODO.md` so the file that is read at the start of **every** session carries only live work. **Nothing here is a to-do.**

`TODO.md`'s `## Done` section keeps a one-line entry for each of these, so the *never redo a closed item without asking* rule still works by grepping there; this file holds the reasoning behind each one.

Items are verbatim as they were closed, newest-moved first in the order they appeared in `TODO.md`. Line numbers and "next up" markers inside them are historical — do not act on them.

---

- [x] **Before the repo goes public** — history rewritten and the GitHub repo recreated from it on 2026-10-05; the owner accepted what stays visible (commit author email, `Claude-Session:` lines, names of the data repo and sibling projects) and the repo was made public the same day. `drive-landscape-data` stays private.

- [x] **Guard the public/private split** — `scripts/check_no_private_data.py`, run by `.githooks/pre-commit` and `tests/test_no_private_data.py`; blocks data paths, data-shaped and credential files, large files and Drive links. Verified 2026-10-05 by a deliberate leak the hook refused.
