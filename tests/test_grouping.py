"""src/grouping.py on made-up distances and texts."""
import numpy as np
import pytest

from src.grouping import combined_distance, medoid, members, two_level

# 0-1 the same thing; 2 the same theme as them; 3-4 another theme; 5 close to nothing.
D = np.array([
    [0.0, 0.1, 0.5, 0.9, 0.9, 1.0],
    [0.1, 0.0, 0.5, 0.9, 0.9, 1.0],
    [0.5, 0.5, 0.0, 0.9, 0.9, 1.0],
    [0.9, 0.9, 0.9, 0.0, 0.6, 1.0],
    [0.9, 0.9, 0.9, 0.6, 0.0, 1.0],
    [1.0, 1.0, 1.0, 1.0, 1.0, 0.0],
])


def test_one_tree_cut_twice_nests_groups_inside_themes():
    same, theme = two_level(D, same_cut=0.25, theme_cut=0.7)
    assert members(same) == [[0, 1]]
    assert members(theme) == [[0, 1, 2], [3, 4]]


def test_an_item_close_to_nothing_stays_alone():
    _, theme = two_level(D, same_cut=0.25, theme_cut=0.7)
    assert all(5 not in rows for rows in members(theme))


def test_cuts_must_be_ordered():
    with pytest.raises(ValueError, match="same_cut <= theme_cut"):
        two_level(D, same_cut=0.8, theme_cut=0.7)


def test_one_item_is_one_group():
    same, theme = two_level(np.zeros((1, 1)))
    assert list(same) == [1] and list(theme) == [1]


def test_medoid_is_the_most_central_row():
    assert medoid(D, [0, 1, 2]) in (0, 1)
    assert medoid(D, [3, 4]) in (3, 4)


def test_either_signal_alone_brings_a_pair_close():
    texts = ["oil the gate hinge", "oil the gate hinge today", "renew passport", "water ferns", "sweep porch"]
    # Rows 2 and 3 share no words but point the same way; the rest are spread out.
    vectors = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
    d = combined_distance(vectors, texts)
    assert d.shape == (5, 5) and np.allclose(d, d.T) and np.allclose(np.diag(d), 0)
    assert d[0, 1] < 0.5      # shared words only
    assert d[2, 3] == 0       # same meaning only
    assert d[0, 4] == 1       # neither
