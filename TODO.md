# TODO

The source of truth for what's left. Read first every session; update in place.

**Format contract** (`tools/todo_archive.py` depends on it): top-level items are
`- [ ]` / `- [x]` lines directly under `## Open work`; `###` sub-headings may
group them; closed items are moved to `docs/TODO_archive.md` by the tool, which
leaves a one-line stub under `## Done`. An open item can be stale — reproduce the
symptom and re-measure the stated cause before acting on it.

## Open work

- [ ] **Phase 1: distil one document** — spec is a proposal awaiting the owner's answers (`docs/SPEC_phase1_distill.md` §9); build order in its §10, starting with embedding the one real list with bge-small via fastembed (owner's choice) and timing it. Done when the Reminders list has been distilled end to end and the owner has confirmed the result in the UI.
- [ ] **Inventory Drive** — `src/inventory.py` is written and tested against a fake service, but has **not yet run against the real Drive**: the owner needs to create the OAuth client and run it on the laptop (steps in `data/DATA.md`). Done when a snapshot is committed to the private repo, its row count is checked against Drive's own total, and the manifest's orphan / not-owned counts have been looked at.
- [ ] **Find the todo lists** — a title search finds only a handful; a keyword search of doc text over-matches (100+ docs, mostly notes and reports), so candidates need a content pass. Done when the owner has confirmed the candidate set.
- [ ] **Collect the todo lists** — each list the owner hands over is filed in the private repo under a neutral id with its original, and converted to `items.jsonl` (`data/DATA.md` "Todo lists"). One so far: an Apple Reminders PDF, 1,355 items, converted with `src/reminders_pdf.py`. Other formats (Google Docs, notes, text) need their own converters as they arrive. Done when the owner says every list is in.
- [ ] **Extract and consolidate todo items** — split lists into items, match duplicates/near-duplicates across lists (text similarity + embeddings; reuse `~/edmonton-open-data-landscape` (confirmed its work 2026-10-05): `src/similarity.py` (TF-IDF), `src/embeddings.py` (fastembed + bge-small-en-v1.5, local, no torch — disk is tight), `src/spotcheck.py` (sample/extend/score label pairs) and its labelling artifact (db capability, `labels` collection, read back with ArtifactData). Its lessons: run all signals from the start and sample label pairs from all of them at once; include pairs the signals rank differently, not only top-5 (top-5 is nearly all "yes" and can't separate methods); strip shared boilerplate before embedding), hand-label a test set to score methods. Done when there is one merged list with every source item accounted for.
- [ ] **Graph the Drive as it stands** — interactive graph of the folder tree (folders and files as nodes, containment as edges; size/age/type as visual channels). Done when the owner can pan, zoom, search and open any node's Drive link.
- [ ] **Graph the Drive by similarity** — second layout arranging folders and files by text similarity (titles + content embeddings), so misfiled and duplicate material sits together regardless of folder. Nothing to copy from `edmonton-open-data-landscape` here: it has clustering only, no projection or front end. Done when the owner can switch between the two layouts on the same nodes.
- [ ] **Clean up Drive** — propose moves/merges/trash from the map; owner approves each batch before anything changes.

## Done

Closed items moved out of `## Open work` live in **`docs/TODO_archive.md`** — one line each below, reasoning there.

- [x] **Before the repo goes public** — 2026-10-05 · `docs/TODO_archive.md`

- [x] **Guard the public/private split** — 2026-10-05 · `docs/TODO_archive.md`
