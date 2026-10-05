# TODO

The source of truth for what's left. Read first every session; update in place.

**Format contract** (`tools/todo_archive.py` depends on it): top-level items are
`- [ ]` / `- [x]` lines directly under `## Open work`; `###` sub-headings may
group them; closed items are moved to `docs/TODO_archive.md` by the tool, which
leaves a one-line stub under `## Done`. An open item can be stale — reproduce the
symptom and re-measure the stated cause before acting on it.

## Open work

- [ ] **Decide how the pipeline reads Drive** — the claude.ai Drive connector works in-session but returns small pages into context; a full inventory needs the Drive API from Python (OAuth token on this box). Done when a script can list every file's metadata without a model in the loop.
- [ ] **Inventory Drive** — one row per file (id, title, mimeType, parent, owner, created/modified/viewed, size) to `data/raw/`; rebuild the folder tree. Done when row count matches Drive's own total and orphans/shared files are counted, not dropped.
- [ ] **Find the todo lists** — a title search finds only a handful; a keyword search of doc text over-matches (100+ docs, mostly notes and reports), so candidates need a content pass. Done when the owner has confirmed the candidate set.
- [ ] **Extract and consolidate todo items** — split lists into items, match duplicates/near-duplicates across lists (text similarity + embeddings; reuse `~/edmonton-open-data-landscape` (confirmed its work 2026-10-05): `src/similarity.py` (TF-IDF), `src/embeddings.py` (fastembed + bge-small-en-v1.5, local, no torch — disk is tight), `src/spotcheck.py` (sample/extend/score label pairs) and its labelling artifact (db capability, `labels` collection, read back with ArtifactData). Its lessons: run all signals from the start and sample label pairs from all of them at once; include pairs the signals rank differently, not only top-5 (top-5 is nearly all "yes" and can't separate methods); strip shared boilerplate before embedding), hand-label a test set to score methods. Done when there is one merged list with every source item accounted for.
- [ ] **Map the Drive** — embed file titles/content, lay out for exploration (sibling: `edmonton-open-data-landscape`). Done when the owner can browse it and spot clusters.
- [ ] **Clean up Drive** — propose moves/merges/trash from the map; owner approves each batch before anything changes.

## Done
