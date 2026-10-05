# SPEC — Phase 1: distil one document

Status: **proposal**, 2026-10-05. Nothing here is locked; §9 lists what the
owner has to decide. Numbers marked *target* are goals, not measurements.
Examples are made up. Parent spec: `docs/SPEC_drive_landscape.md` — this phase
comes before its Drive-graph stages.

## 1. What phase 1 delivers

Put **one document** in — a long todo list, or a scattered doc where only some
sections are todo-related — and get out **a new, shorter list**: the distilled
version of the old one.

1. **Ingest.** The document becomes ordered blocks; each block is a todo item,
   or prose, or a heading.
2. **Group.** Items are sorted into groups by what they are about.
3. **Review.** An agent (a Claude Code session) works through the groups:
   names them, merges, splits, drafts the distilled wording, and marks what it
   is unsure of.
4. **Confirm.** The owner checks the result in a small local UI and confirms,
   fixes or rejects.
5. **Export.** A new list is written, each entry citing the old items it
   replaces.

"Grouped by sentiment" is read here as **grouped by meaning / theme**, not by
positive-or-negative mood (§9, question 1).

**Not in phase 1:** matching across documents, the Drive inventory and graph,
Drive clean-up, writing back to Google Docs or Reminders, more than one user.

## 2. Principles

- **Local and light.** Runs on an old laptop, offline once installed. No
  torch, no database server, no vector database, no Node build, no pandas.
- **The agent does the judgement; the algorithm only proposes.** With an agent
  in the loop, embeddings need to be good enough to put likely-related items
  next to each other — not good enough to be trusted alone.
- **Files are the interface.** State is plain text files in the private data
  repo. The agent's commands and the owner's UI are two front ends over the
  same functions and the same files.
- **Every item is accounted for.** At any moment each source item is exactly
  one of: in a group, kept on its own, dropped with a reason, or undecided. The
  export states how many are still undecided.
- **Nothing private in this repo** (`data/DATA.md`).

## 3. Stack

| Layer | Choice | Why | Rejected |
|---|---|---|---|
| Language | Python 3.12, standard library first | already the repo's language | — |
| Text → items | `pdfplumber` for Reminders PDFs (exists); a Markdown / plain-text reader written here | no new dependency for the common case | pandoc, unstructured — heavy |
| Word similarity | TF-IDF, 1–2-grams (`scikit-learn`) | instant; catches shared rare words and names | — |
| Meaning similarity | **`BAAI/bge-small-en-v1.5` run locally through `fastembed`** (ONNX Runtime, no torch; fastembed downloads a quantised copy, about 65 MB) | the owner's choice, 2026-10-05: the same setup as `edmonton-open-data-landscape`, so results and code carry over; no need to go to a minimum-size model | `model2vec` static embeddings — smaller, but a second setup to learn for no stated need; `sentence-transformers` — needs torch |
| Neighbours | brute-force cosine in `numpy` | a few thousand items is a few million multiplications | FAISS, a vector database |
| Grouping | `scikit-learn` agglomerative clustering with a distance cut, at two levels (§5) | no group count to guess; leaves loners alone | k-means (needs k, forces every item into a group) |
| State | JSON Lines files + an append-only decision log (§6) | diffable in git, safe for agent and owner to write at once, gives undo | SQLite — binary, not diffable |
| Agent interface | a command-line tool with `--json` output, plus a project skill describing the routine | every Claude Code session can already run a command | an MCP server — more to run, nothing gained yet |
| Owner UI | one static HTML page with plain JavaScript, served by a small standard-library server on `127.0.0.1` | no framework to install; also works from the server over an SSH tunnel | Streamlit (large install, awkward for regrouping); a hosted Claude artifact (the text would leave the machine) |

New dependencies: `numpy`, `scikit-learn`, `fastembed` (which brings
`onnxruntime`). *Target:* under 1 GB of memory, and a 1,500-item document
grouped in a few minutes at most on the laptop. **None of this has been
measured here yet.** The one known figure is from the other project: about 4
minutes for 920 texts on the server, but those were long texts cut at 512
tokens; todo items are a sentence each and should be far quicker. The first
build task is to time it on the one real list we have, and to check the laptop
can install `onnxruntime` (§9, question 5). Vectors are cached per document, so
the cost is paid once per document, not per session.

## 4. Ingest

Every format is converted to the same thing: **an ordered list of blocks**.

| Field | Meaning |
|---|---|
| `n` | position in the document, from 1 |
| `kind` | `item`, `prose` or `heading` |
| `text` | the block's text |
| `path` | the headings above it, outermost first |
| `level`, `parent` | nesting, for sub-items |
| `detail` | a date or note attached to the item, if any |

- **Reminders PDF** — done (`src/reminders_pdf.py`); every block is an item.
- **Markdown / plain text** — new. Headings give `path`; bullets, numbered
  lines and checkbox lines are items; everything else is prose. A checked or
  struck-through item is marked done.
- **Google Docs** — exported to Markdown, then read by the same reader. Phase 1
  takes the exported file (the owner downloads it, or an agent session fetches
  it); the automatic pull belongs to the Drive stages.

**Scattered documents.** In a doc that mixes todo sections with notes, the
reader does not decide what is "todo-related". It keeps every block and makes a
first guess per section (mostly short list lines → likely todos). The agent
then marks each section **in** or **out**, and the owner can overrule in the
UI. Prose inside an "in" section is shown beside its items as context, and can
be promoted to an item. Nothing is deleted: an "out" section is recorded as out.

**Order and age.** A block's position is kept, and a document can declare
which end is older (§9, question 2). Where a real date exists (an item's date
line, a dated heading) it is used instead. Age is then shown everywhere: items
in a group are listed oldest first, and each group shows its oldest item and
how much of the document it spans. Age never removes anything by itself.

## 5. Grouping

Two levels, because distilling needs both:

- **Same thing** — near-duplicates and rewordings of one task. Tight cut. These
  collapse into one line of the new list.
- **Same theme** — items about one area. Looser cut. These become the sections
  of the new list.

Both similarity signals are computed for every item from the start; a pair
counts as close when either says so strongly or both agree moderately. An item
close to nothing stays on its own — a long personal list will have many, and
forcing them into groups would make every group worse. An item's heading path
is added to its text before comparing, so "call them" under two different
headings is not a match.

The cuts start as guesses. **The review itself is the labelling:** every
confirm, merge and split is recorded (§6), so after the first document there is
a set of owner-approved groups to score the signals against and tune the cuts —
no separate labelling round.

## 6. State

In the private repo, one folder per document:

```
todo/<id>/
  original.*           as received
  items.jsonl          blocks (§4)
  work/
    proposal.json      what the algorithm suggested, and with which settings
    log.jsonl          every decision, appended, never rewritten
    distilled.md       the exported new list
```

`log.jsonl` is the only thing the agent and the UI write. One line per
decision: who (`agent` or `owner`), when, what (create / rename / merge / split
a group, move an item, keep or drop an item with a reason, set a section in or
out, set a group's distilled wording, mark a group for the owner, **confirm**).
The current state is the log replayed from the top.

Why a log rather than one state file: two writers cannot overwrite each other;
undo is "ignore the last line"; the git diff reads as a history; and it records
which groups the owner actually confirmed, as opposed to ones only the agent
touched. Vectors are derived and are not committed.

## 7. Agent interface

One command with sub-commands; each prints a short, bounded JSON answer so a
session never has to read a whole document into its context.

| Command | Does |
|---|---|
| `status <id>` | counts: items, groups, confirmed, undecided, marked for the owner |
| `ingest <file>` / `propose <id>` | build the blocks / build the proposal |
| `sections <id>` | each section with its first guess, a few sample lines, in / out |
| `groups <id> [--unreviewed] [--limit N]` | group summaries: size, age span, sample items |
| `show <id> <group>` | one group's items in age order, with their nearest outside neighbours |
| `rename`, `merge`, `split`, `move`, `keep`, `drop`, `section`, `draft`, `flag` | the edits, each one log line |
| `export <id>` | write `distilled.md`; report what is still undecided |

A project skill gives the routine: check status → settle sections → go through
unreviewed groups a batch at a time → draft wording → flag anything doubtful
for the owner → stop. The agent never confirms; **only the owner confirms**.

## 8. Owner UI

For final checks, not for doing the sorting by hand.

- A queue: groups flagged by the agent first, then unconfirmed, then confirmed.
- One group per screen: its name, the drafted line, the old items in age order
  with their place in the original, and why they were put together.
- Actions: confirm; edit the name or the line; pull an item out; send an item
  to another group; split; drop with a reason; undo.
- A second view for sections of a scattered doc: in / out, with the text.
- A progress count, and a preview of the new list as it stands.
- Keyboard-first — a 1,355-item list is a few hundred groups to step through.
- Reads and writes only through the same functions as §7, on `127.0.0.1`.

**The new list** (`distilled.md`): themes as sections, one line per confirmed
group or kept item, ordered within a section by age; an appendix maps each line
to the old items it replaces, and lists what was dropped and why. Re-running
the export after more review rewrites it from the log, so edits belong in the
UI, not in the exported file.

## 9. For the owner to decide

1. **"Sentiment"** — is grouping by theme / meaning what you meant? Or do you
   also want a second axis, such as the *kind* of item (task, idea, someday,
   thing to buy, reference) or its tone (urgent, nagging, wishful)?
2. **Which end of the Reminders list is older** — and does older mean
   "long-standing, matters" or "probably stale"? It changes what the UI
   highlights.
3. **Done items** — the Reminders export cannot show done / not-done. Does that
   list include completed reminders?
4. **The agent reads the text.** A Claude Code session grouping your items
   means the item text passes through Claude, as it does in any session. The
   pipeline itself would call no hosted service. `docs/SCOPE.md` has been
   reworded to say this; say so if you want the agent kept away from some
   documents.
5. **The laptop** — CPU, memory, free disk, distro and Python version. An old
   or 32-bit machine can change which packages install at all.
6. **Where the new list lives** — a Markdown file in the private repo is the
   phase-1 answer. Back into Reminders or a Google Doc would be a later step.

## 10. Build order

1. Embed the real list with the chosen setup, copying the other project's
   pins and call; measure time, memory and install size here and on the laptop.
2. State: the log, replay, and the accounted-for check — with tests first.
3. `propose`: two-level grouping; `status`, `groups`, `show`.
4. Edit commands and `export`; the skill. At this point an agent can distil the
   Reminders list end to end without a UI.
5. The UI.
6. The Markdown reader and section in / out, for scattered docs.
7. Score the signals against the confirmed groups; tune the cuts.
