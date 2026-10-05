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
