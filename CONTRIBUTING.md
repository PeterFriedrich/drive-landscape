# Contributing

## Development Pipeline

Work follows this sequence. Do not skip steps — each one informs the next.

| Step | Artifact | Purpose |
|------|----------|---------|
| 1. Spec | `docs/SPEC_<phase>.md` | Defines what to build, inputs/outputs, and acceptance criteria |
| 2. Architecture | `docs/ARCHITECTURE.md` | Defines module contracts, data flow, and key technical decisions |
| 3. Implementation | `src/*.py` | One module at a time, in data flow order |
| 4. Tests | `tests/*.py` | Per module, using synthetic data only |

For new phases, start at step 1 and write a new spec before touching any code.

### AI-assisted workflow

This project uses Claude Code. The pipeline above is designed for it:

- **Spec first** — a written spec gives the AI unambiguous scope. Without it,
  the AI fills gaps with assumptions.
- **Architecture before implementation** — explicit module interfaces prevent
  different design decisions across separate conversations.
- **One module at a time** — implement, review, then move on.
- **Tests alongside each module** — while the design intent is still in context.
- **`CLAUDE.md` is the AI's working memory** — a convention that is not written
  there does not persist across sessions.
- **A decision is a test first, prose second** — `docs/DECISIONS.md` rows cite
  the guard that protects them.

## Getting Started

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
git config core.hooksPath .githooks   # NOT cloned automatically; see CLAUDE.md
.venv/bin/python -m pytest tests/ -q  # synthetic data only — no downloads needed
```

Raw data files are not committed. See `data/DATA.md` for sources and download
instructions.

## Code Conventions

- **One file per processing step** in `src/` — each module is independently runnable
- **No silent data drops** — flag unmatched or missing records explicitly (count + examples)
- **No hardcoded paths** — file paths are constants at the top of the entry
  point, passed down as arguments
- **Rendering modules contain no analysis logic**

## Project Structure

```
/
├── data/
│   ├── raw/                  # Downloaded inputs — not committed
│   ├── processed/            # Intermediate outputs from each step
│   └── DATA.md               # Source details, column names, known quirks
├── docs/                     # Specs, decisions, ledgers — see CLAUDE.md
├── scripts/                  # Guards (check_*.py) and one-off operational scripts
├── src/                      # One module per processing step
├── tests/                    # Synthetic-data tests + repo invariants
├── tools/                    # Maintenance tooling (todo_archive, retrieval_report)
├── session-summary/          # Handoffs; archive/ holds all but the newest 3
├── output/                   # Final artifacts — not committed
├── CLAUDE.md
├── TODO.md
└── README.md
```
