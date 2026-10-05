# SPEC — drive-landscape

Status: draft, 2026-10-05. Written from the scoping session; nothing here is
locked unless `docs/DECISIONS.md` has a row for it. Examples are made up — this
repo carries no real Drive names (see §7).

**Order of work changed 2026-10-05:** the first thing to build is distilling
one document at a time — `docs/SPEC_phase1_distill.md`. The Drive inventory,
graph and cross-list matching below come after it.

## 1. Purpose

One person's Google Drive has grown for years without upkeep. Two problems:

1. **Todo lists everywhere.** Many long todo / priorities / "actionables" docs,
   written at different times, overlapping, partly done, none authoritative.
2. **No overview of the Drive.** Folders with near-identical purposes, several
   catch-all folders, old material mixed with current.

The project produces:

- **A. One consolidated todo list** — every item from every source list, with
  duplicates and near-duplicates merged, and each merged item traceable back to
  the lists it came from.
- **B. An interactive graph of the Drive, in two layouts over the same nodes:**
  - *as it stands* — the folder tree (containment);
  - *by similarity* — folders and files arranged by what they are about, so
    duplicates and misfiled material sit together regardless of folder.
- **C. A clean-up plan** derived from B — proposed moves, merges and trashing,
  applied only after the owner approves each batch.

## 2. Not in scope

See `docs/SCOPE.md`. In short: no unattended changes to Drive, no Drive data in
this repo, no hosted or multi-user service.

## 3. Who uses it and where it runs

- Single user, the Drive's owner. No other audience for the data; the code is
  meant to be public.
- **Usual machine: the owner's Linux work laptop** — room to install anything
  (torch is fine there), a local browser for OAuth consent.
- **Also: an Oracle free-tier ARM64 server** (Oracle Linux 8, 4 cores, disk
  about 88% full) where Claude Code sessions run. Heavy dependencies must stay
  optional so the code still imports and tests there.
- Python 3.12, venv per repo. CI is offline and secret-free: tests use fakes
  and made-up fixtures, never the network or real data.

## 4. Data

| Source | How | Status |
|---|---|---|
| Drive metadata (every file and folder: id, name, type, parents, owner, shared, trashed, created / modified / viewed times, size, checksum, link) | Drive API v3, read-only OAuth, `src/inventory.py` | written, tested against a fake service, **not yet run on the real Drive** |
| Doc text (Google Docs first; then Sheets, PDFs, plain text as needed) | Drive API export, same token | not started |
| Hand labels ("are these two items the same?") | labelling page, see §6.3 | not started |

Observed in a first look (through a chat connector, not the pipeline): at least
100 folders, several levels deep; a handful of docs titled as todo lists; a
keyword search of doc text for "todo" returns 100+ docs, mostly notes and
reports. So **todo lists cannot be found by title, and keyword search
over-matches** — finding them needs a pass over content.

Details and quirks: `data/DATA.md`.

## 5. Pipeline

Separate, independently runnable modules in `src/`. Each stage reads the
previous stage's files and writes its own. No silent drops: anything unmatched,
unreadable or skipped is counted and reported.

| # | Stage | Input → output | Status |
|---|---|---|---|
| 1 | Inventory | Drive API → `files.jsonl.gz` + `manifest.json` per date | written |
| 2 | Tree | inventory → nodes and containment edges, per-folder rollups (file count, bytes, newest / oldest change) | next |
| 3 | Tree graph | tree → interactive page (layout 1) | next |
| 4 | Text pull | inventory → one text file per doc, with a manifest of what could not be exported | planned |
| 5 | Similarity | text → per-item and per-file vectors and top-k neighbours, from more than one method side by side | planned |
| 6 | Similarity graph | vectors → 2-D positions for the same nodes (layout 2) | planned |
| 7 | Todo extraction | text → one row per todo item (text, source doc, position, done / not done, section heading) | planned |
| 8 | Todo matching | items → groups of same / near-same items across lists | planned |
| 9 | Labelling + scoring | sampled pairs → hand labels → precision per method | planned |
| 10 | Consolidated list | groups → one list, each entry citing its sources | planned |
| 11 | Clean-up proposals | graph + similarity → proposed moves / merges / trash, for approval | later |

## 6. Design notes

### 6.1 The graph (B)

- Nodes: folders and files. Edges in layout 1: containment.
- Visual channels to use: size (bytes or item count), age (last modified /
  last viewed), type, owned vs shared, trashed.
- Must have: pan, zoom, search by name, collapse / expand a folder, click
  through to the item in Drive, and **a switch between the two layouts on the
  same nodes** so a file can be followed from where it is filed to what it
  resembles.
- Runs locally as a static page reading a data file from the private repo.
  Nothing is uploaded.
- A folder has no text of its own; its position in layout 2 has to be derived
  from its name and its contents.

### 6.2 Similarity (5, 8)

Prior work to reuse, from the owner's `edmonton-open-data-landscape` project
(920 short catalogue texts):

- TF-IDF (1–2-grams, sublinear tf) with cosine; and embeddings with
  `fastembed` + `BAAI/bge-small-en-v1.5` (ONNX, no torch), about 4 minutes for
  920 texts on the server. Top-k neighbours, no thresholds.
- The two scored about the same there (49% vs 47% of top-5 neighbours in the
  same reference category; chance 5%) and agreed only loosely on which
  neighbours (top-10 Jaccard 0.33).
- Shared boilerplate dominated both signals. Todo lists built from a template
  will have the same problem: strip repeated headers before comparing.

### 6.3 Labelling (9)

The same project has a labelling page (a Claude artifact with a small shared
database): cards of candidate pairs, Yes / No / Unsure, live precision per
method; labels are read back and scored by a script. Lessons from it, to apply
from the start:

- Run every method first, then sample the pairs to label from all of them at
  once — adding a method later forced a second labelling round.
- Do not label only everyone's top-5: those are nearly all "yes" and cannot
  separate the methods. Include pairs the methods rank differently and
  near-misses.
- Because the labelled text here is private, the labelling page must stay
  private to the owner, or run locally.

### 6.4 Todo consolidation (A)

- An item is the unit, not a document. Lists nest; an item's meaning often
  depends on its heading ("Taxes → call them"), so the heading path travels
  with the item.
- Done-ness matters: checked boxes, strikethrough, "DONE" markers. A done item
  in one list and an open copy in another is a finding, not a duplicate to
  merge silently.
- Every source item must appear in the output exactly once, either on its own
  or inside a merged group — the count in equals the count accounted for.
- Lists have dates (created, last modified). When copies differ, the newer one
  is probably the current wording, but the older may carry detail.

### 6.5 Clean-up (C)

- Proposals only: a reviewable list of "move X to Y", "these two folders look
  like one", "not opened since <year>". The owner approves a batch; only then
  does anything change, through a separate write-scoped step.
- Prefer reversible operations (move, rename) over trashing; trash over delete.
- Log every applied change with before / after so it can be undone.

## 7. Privacy

- **Code here, data elsewhere.** All Drive-derived data — names, ids, text,
  todo items, vectors, labels, rendered graph data — lives in a separate
  private repo cloned at the gitignored `data/raw/private/`.
- No real name, title, id or text in any tracked file, test, commit message or
  PR. Fixtures are invented.
- OAuth client file and token live outside both repos
  (`~/.config/drive-landscape/`). Scope is `drive.readonly` until the clean-up
  step, which needs its own consent.
- Doc text is processed locally. Sending it to a hosted embedding or LLM API is
  not assumed and would be a decision for the owner.

## 8. Open questions

1. **Graph front end.** Which library suits a few thousand to tens of
   thousands of nodes with collapse / expand, search, and an animated switch
   between a tree layout and a 2-D similarity layout — in a static page?
2. **Layout 2.** UMAP / t-SNE projection, a force layout on the k-nearest-
   neighbour graph, or something that keeps folders visibly grouped? How should
   a folder's position be derived from its contents?
3. **Mixed content.** Files range from one-line notes to long reports, plus
   spreadsheets, PDFs, images and code. What to embed for each (title only,
   title + first N tokens, chunk and average), and what to do with files that
   have no usable text?
4. **Embedding model on the laptop**, where torch is allowed: is a larger model
   worth it over bge-small for short todo items and for whole documents? Is
   model2vec good enough to be the server-side fallback?
5. **Finding the todo lists.** A classifier over doc structure (share of short
   bulleted / checkbox lines, imperative verbs), embeddings against a few
   known lists, or a local LLM pass? What is the cheapest reliable method?
6. **Extracting items from Google Docs.** Export as Markdown / HTML versus the
   Docs API structure — which preserves nesting, checkboxes and strikethrough?
7. **Matching todo items.** Items are very short; embeddings and TF-IDF both
   behave differently on a few words. Does prepending the heading path help?
   Top-k neighbours versus clustering versus a threshold — and how to turn
   pairwise matches into groups without chaining unrelated items together?
8. **Labelling design.** How many pairs, sampled how, to separate two or three
   methods with reasonable confidence?
9. **The consolidated list's home.** One Google Doc, a Markdown file, a sheet,
   or a task app? What format keeps the source links and survives re-running
   the pipeline after the owner edits it?
10. **Keeping it current.** Re-run on demand, or track Drive changes
    incrementally (the API's changes feed)?
