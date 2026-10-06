"""Two-level grouping of a document's items: same thing, and same theme.

Two signals for every pair of items: cosine of their embeddings (meaning) and
cosine of their TF-IDF vectors (shared words). They are folded into one
distance that is small when either signal is strong or both are moderate. One
average-linkage tree over that distance is then cut at two heights, so every
same-thing group sits inside one theme. An item close to nothing stays alone.

The cuts are guesses until there are owner-confirmed groups to score against
(docs/SPEC_phase1_distill.md §5).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

SAME_CUT = 0.25
THEME_CUT = 0.70


def word_similarity(texts: Sequence[str]) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer

    try:
        tfidf = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True).fit_transform(texts)
    except ValueError:  # every text is stop words only
        return np.eye(len(texts))
    sim = (tfidf @ tfidf.T).toarray()
    np.fill_diagonal(sim, 1.0)
    return sim


def combined_distance(vectors: np.ndarray, texts: Sequence[str]) -> np.ndarray:
    """0 = the same, 1 = nothing in common. `vectors` are unit length, one row per text."""
    meaning = vectors @ vectors.T
    # Embedding cosines of unrelated short texts sit well above zero; measure
    # from the document's typical pair, not from 0.
    floor = float(np.median(meaning[np.triu_indices(len(texts), k=1)])) if len(texts) > 1 else 0.0
    meaning = np.clip((meaning - floor) / (1.0 - floor), 0.0, 1.0)
    words = np.clip(word_similarity(texts), 0.0, 1.0)
    distance = (1.0 - meaning) * (1.0 - words)
    np.fill_diagonal(distance, 0.0)
    return (distance + distance.T) / 2


def two_level(distance: np.ndarray, same_cut: float = SAME_CUT, theme_cut: float = THEME_CUT) -> tuple[np.ndarray, np.ndarray]:
    """A same-thing label and a theme label per item, from one tree cut at two heights."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    if not 0 <= same_cut <= theme_cut:
        raise ValueError(f"need 0 <= same_cut <= theme_cut, got {same_cut} and {theme_cut}")
    n = len(distance)
    if n < 2:
        return np.ones(n, dtype=int), np.ones(n, dtype=int)
    tree = linkage(squareform(distance, checks=False), method="average")
    return fcluster(tree, same_cut, criterion="distance"), fcluster(tree, theme_cut, criterion="distance")


def members(labels: np.ndarray) -> list[list[int]]:
    """Row indexes per label with two or more rows, each ascending, ordered by first row."""
    by_label: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        by_label.setdefault(int(label), []).append(i)
    return sorted((rows for rows in by_label.values() if len(rows) > 1), key=lambda rows: rows[0])


def medoid(distance: np.ndarray, rows: list[int]) -> int:
    """The row closest on average to the others in `rows`."""
    sub = distance[np.ix_(rows, rows)]
    return rows[int(np.argmin(sub.sum(axis=1)))]
