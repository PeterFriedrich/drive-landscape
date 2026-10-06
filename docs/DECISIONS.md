# Decisions Index

Append-only. **One ROW per locked decision** — when, what, why (including what
was rejected), and a pointer to where the argument lives in full. When a decision
locks, add a row; when one is superseded, strike it (`~~...~~`) or mark it
`SUPERSEDED <date>` in place and add the successor — don't delete history.

**What a row owes you:**

1. ⚠️ **EVERY ROW CARRIES A POINTER TO A DOC** — not only to code. Code moves;
   the argument has to live somewhere prose can hold it.
   `scripts/check_doc_citations.py` checks that every pointer resolves.
2. **The row is a self-contained summary** and may paraphrase the argument.
3. **The pointer is the authority.** When a row and its target disagree, the
   target wins and the row gets fixed.
4. **A row names the test that protects it**, or carries `[unverifiable]`.
   `scripts/check_decisions_log.py` enforces this on the merge gate (and that a
   superseded row is marked where it stands).

| When | Decision | Full reasoning |
|------|----------|----------------|
| 2026-10-05 | Code in this repo (to go public), all Drive-derived data in the private repo `drive-landscape-data` cloned at the gitignored `data/raw/private/`; nothing read from Drive goes in a tracked file. Rejected: one private repo holding both (owner wants the project public). Guarded by `check_no_private_data.py` (pre-commit hook and `test_repo_tracks_no_private_data`): paths, data-shaped and credential files, size, Drive links. It cannot recognise a private name or todo text typed into a doc. | `data/DATA.md` |
| 2026-10-05 | Embeddings are `BAAI/bge-small-en-v1.5` run locally through `fastembed` (no torch), the same setup as `edmonton-open-data-landscape`; TF-IDF runs beside it. Rejected: `model2vec` static embeddings (the owner sees no need to go to a minimum-size model). `[unverifiable]` — no embedding code exists yet. | `docs/SPEC_phase1_distill.md` §3 |
| 2026-10-05 | "Grouped by sentiment" means grouped by theme / meaning, and theme is the only axis for now. Rejected for now: a second label per item for its kind (task, idea, someday, thing to buy, reference) or its tone (urgent, nagging, wishful) — kind can be added later as a tag proposed during review. `[unverifiable]` — no grouping code exists yet. | `docs/SPEC_phase1_distill.md` §9 |
| 2026-10-05 | An item that holds several todos is split by the owner, by hand, into one item per todo (`break`, owner only); the UI pre-fills the split sentence by sentence and nothing is saved until the owner saves it. Rejected: splitting every item into sentences automatically before grouping (the owner wants to make each split), and a blank box (756 of the first list's 1,355 items have more than one sentence). Guarded by `tests/test_state.py::test_a_break_that_makes_no_sense_is_refused`, `::test_parts_are_items_like_any_other` and `::test_account_catches_a_lost_part`. | `docs/SPEC_phase1_distill.md` §6 |
| 2026-10-05 | Themes are review state in the log, not only a suggestion in `proposal.json`: a theme is a named section holding whole groups and items that stand alone (undecided or kept); only the owner confirms one; changing its name or members unconfirms it. Rejected: themes holding kept items only (the proposal would have to keep 1,077 items nobody has looked at to seed them). Guarded by `tests/test_state.py::test_a_theme_line_that_makes_no_sense_is_refused`, `::test_changing_a_confirmed_theme_unconfirms_it`, `::test_account_catches_a_theme_holding_what_it_cannot`. | `docs/SPEC_phase1_distill.md` §6 |
| 2026-10-06 | "Later" is a third outcome beside kept and dropped: a mark on a group or a kept item (`later`, on or off) that keeps it on the new list, in one "Later" section below all the themes, tagged with its theme; marking an undecided item keeps it, and the mark unconfirms nothing. Rejected: de-prioritized items leaving the list like dropped ones without a reason (the owner: on the list, at the bottom). Guarded by `tests/test_state.py::test_later_marks_a_group_or_a_kept_item_and_keeps_an_undecided_one`, `::test_later_refuses_what_it_cannot_mark` and `tests/test_distill.py::test_export_writes_confirmed_groups_and_kept_items_by_theme`. | `docs/SPEC_phase1_distill.md` §8 |
