# SCOPE — what this project deliberately does not do

The one hand-kept input to the Claude web brief (`scripts/make_brief.py`, setup
in `docs/CLAUDE_WEB.md`). Everything else in the brief is generated from files
the repo already maintains; this is the list an outside reviewer can't derive —
ideas that were considered and turned down, so they stop coming back as
recommendations.

One bullet each: **the thing**, then why not, and a pointer if a decision row
or doc holds the argument. A turned-down idea that has a locked decision needs
no bullet here — the brief already carries `docs/DECISIONS.md`.

## Out of scope

- **Changing anything in Drive automatically** — moves, renames, trashing and edits happen only after the owner approves that specific batch; the pipeline is read-only until then. `docs/SPEC_drive_landscape.md` §6.5.
- **Putting Drive data in this repo** — names, ids, text, vectors, labels and rendered graph data all live in the private data repo; this repo is code and is meant to be public. `data/DATA.md`.
- **A hosted or multi-user service** — one user, run locally; the graph is a static page reading a local file.
- **Driving the pipeline through a chat connector** — the claude.ai Drive connector returns results into the model's context and is too costly for a full inventory or text pull; the pipeline uses the Drive API from Python.
- **Sending doc text to a hosted embedding or LLM API by default** — the text is personal; local processing is the baseline and anything else is the owner's call.
