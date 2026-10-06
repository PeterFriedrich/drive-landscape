# Data Sources

Reference for raw input files. Update this file when you discover column name
quirks, encoding issues, or anything unexpected. Do not rely on memory — write it
down here. A defect in the *publisher's* data goes in `docs/DATA_ISSUES.md`,
with a status saying whether they have been told.

**Download completeness:** an API that pages or caps (`$limit` on Socrata, for
instance) truncates *silently* — it returns exactly that many rows with no
error. Every downloader verifies its row count against the live server count
and fails hard on a mismatch.

**Vintage:** record, per source, the dataset id, the retrieval timestamp and
the publisher's own last-updated stamp. A guard must measure the DATA (row
counts, max date in the file), never a metadata string that can go stale
while the guard stays green.

## Sources

### <source name>
- **Publisher / URL:**
- **Dataset id:**
- **Retrieved:** <date> — **publisher last-updated:** <date>
- **Rows / columns:**
- **CRS (if spatial):**
- **Quirks:**

## Where the data lives

Code is in this repo (meant to be public). Data is in the private repo
`PeterFriedrich/drive-landscape-data`, cloned as a nested repo at
`data/raw/private/`, which the `data/raw/*` rule in `.gitignore` keeps out of
this repo. Derived outputs go to `data/processed/` and `output/`, also ignored;
anything derived that is worth keeping is committed to the private repo, not here.

Everything read from Drive counts as private: file and folder names, ids, doc
text, todo items, embeddings and label files. Tracked files here use made-up
examples only.

Guard: `scripts/check_no_private_data.py` refuses anything under `data/` or
`output/` beyond the placeholders, data-shaped and credential files, files over
500 KB, and Google Drive / Docs links. `.githooks/pre-commit` runs it on every
commit (enabled by `./bootstrap.sh`, which sets `core.hooksPath`), and
`tests/test_no_private_data.py` runs it on the merge gate. It cannot recognise
a private file name or todo text typed into a doc — that part is on the author.

Setup on a new machine:

```bash
git clone https://github.com/PeterFriedrich/drive-landscape-data.git data/raw/private
```

## Drive inventory (`src/inventory.py`)

`python -m src.inventory` writes `data/raw/private/inventory/<date>/files.jsonl.gz`
(one Drive API `files` resource per line, folders included, trashed included)
and `manifest.json` (counts: total, folders, owned / not owned, trashed, no
parent, parent not in inventory, bytes, per MIME type).

Auth: put the OAuth client file (Google Cloud Console → Desktop app, Drive API
enabled) at `~/.config/drive-landscape/credentials.json`. The first run opens a
browser for consent and caches `token.json` beside it. Scope is
`drive.readonly`. Override the directory with `--config-dir` or
`DRIVE_LANDSCAPE_CONFIG`.

Quirks to expect: a file can have no `parents` (shared with the owner one file
at a time, or orphaned); `size` is absent for Google Docs/Sheets/Slides and
folders, so `bytes` undercounts them.

## Todo lists (`data/raw/private/todo/`)

One folder per list, under a neutral id (`todo-001`, …); `todo/manifest.json`
maps each id to its original name, source app, date received and checksum. The
real name stays in the manifest so that paths never carry it.

Each folder keeps the **original file as received** plus what was extracted:

- `items.jsonl` — one todo item per line: `n` (order in the list), `level`
  (0 = top, 1 = subtask), `parent` (`n` of the item above it, or null), `text`,
  `detail` (a date line under the item, or null), `bold`, `page`. This is what
  the matching step reads.
- `list.md` — the same list as a Markdown checklist, for reading and diffing.
- `extract_summary.json` — the counts from the run.
- `work/vectors.npy` — one unit-length embedding per item, row i = line i of
  `items.jsonl` (`python -m src.embed data/raw/private/todo/<id>`). A local
  cache, gitignored in the private repo: vectors differ slightly between
  machines, so rebuild it rather than copy it.
- `work/part_vectors.npz` — the vectors of the parts the owner split items
  into (`break`), keyed by the part's text and filled in by `src/distill.py`
  the first time a command needs them. A local cache like `vectors.npy`, and
  gitignored the same way.
- `work/proposal.json` — what `python -m src.distill propose <id>` suggested:
  the settings, the counts, the same-thing groups and the themes, each a list
  of item numbers. Committed in the private repo.
- `work/log.jsonl` — the review decisions, one per line, appended and never
  rewritten (`src/state.py`, whose docstring gives the line format). Committed
  in the private repo: it is the record of what the owner confirmed. A
  `break` line also holds item text: the parts the owner split an item into,
  which exist nowhere else (ids `<n>.1`, `<n>.2`, ... — strings, where `n` is
  a number).
- `work/embed_summary.json` — model, item count, timings and peak memory of
  that run, on the machine that ran it.

### Apple Reminders PDF (`src/reminders_pdf.py`)

`python -m src.reminders_pdf LIST.pdf --out data/raw/private/todo/<id>`. The
export has a real text layer (no OCR needed) and prints the list's own item
count on page 1; the converter compares its item count with it and exits 1 if
they differ, or if any line or marker was left unplaced.

Quirks: **done / not-done is not recoverable** — the export draws every marker
identically. A wrapped title and a title containing a line break look the same;
both are joined with a space. A list's sections, if it has any, are not marked
in a way seen so far (only one list has been converted).
