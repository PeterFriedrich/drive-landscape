"""Embed a document's items, one vector per item.

    python -m src.embed data/raw/private/todo/todo-001

Reads <doc>/items.jsonl and writes <doc>/work/vectors.npy (row i is item i of
items.jsonl, unit length) and <doc>/work/embed_summary.json (counts, timings,
peak memory). Both are private — see data/DATA.md. Logs counts and timings
only, never item text.

Vectors differ slightly between machines, so vectors.npy is a local cache: it
is rebuilt here rather than copied from another machine.
"""
from __future__ import annotations

import argparse
import json
import logging
import resource
import time
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

log = logging.getLogger("embed")

MODEL = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 32
CACHE_DIR = Path.home() / ".cache" / "fastembed"  # fastembed's default is a temp dir

EmbedFn = Callable[[Sequence[str]], np.ndarray]


def fastembed_fn(model: str = MODEL, cache_dir: Path = CACHE_DIR) -> EmbedFn:
    from fastembed import TextEmbedding

    encoder = TextEmbedding(model_name=model, cache_dir=str(cache_dir))

    def embed(texts: Sequence[str]) -> np.ndarray:
        # A batch is padded to its longest text, so one long item slows a whole
        # default batch of 256. Similar lengths together, in small batches: same
        # vectors, about 4x faster and a quarter of the memory on the real list.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        ordered = np.array(list(encoder.embed([texts[i] for i in order], batch_size=BATCH_SIZE)), dtype=np.float32)
        vectors = np.empty_like(ordered)
        vectors[order] = ordered
        return vectors

    return embed


def read_items(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def embed_items(items: list[dict], embed: EmbedFn) -> np.ndarray:
    """One unit-length row per item, in order. An item with no text is an error, not a skip."""
    blank = [it["n"] for it in items if not it["text"].strip()]
    if blank:
        raise ValueError(f"{len(blank)} items have no text (n = {blank[:10]}); nothing embedded")
    vectors = np.asarray(embed([it["text"] for it in items]), dtype=np.float32)
    if vectors.ndim != 2 or len(vectors) != len(items):
        raise ValueError(f"{len(items)} items in, vectors of shape {vectors.shape} out")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.all(norms > 0):
        raise ValueError(f"{int((norms == 0).sum())} zero vectors")
    return vectors / norms


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("doc", type=Path, help="document folder holding items.jsonl")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")

    items = read_items(args.doc / "items.jsonl")
    t0 = time.perf_counter()
    embed = fastembed_fn(args.model, args.cache_dir)
    t1 = time.perf_counter()
    vectors = embed_items(items, embed)
    t2 = time.perf_counter()

    work = args.doc / "work"
    work.mkdir(exist_ok=True)
    np.save(work / "vectors.npy", vectors)
    summary = {
        "model": args.model,
        "items": len(items),
        "dimensions": int(vectors.shape[1]),
        "median_text_chars": int(np.median([len(it["text"]) for it in items])),
        "load_seconds": round(t1 - t0, 2),
        "embed_seconds": round(t2 - t1, 2),
        "items_per_second": round(len(items) / (t2 - t1), 1),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    (work / "embed_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    log.info("wrote %s %s", work, json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
