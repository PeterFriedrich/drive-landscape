"""src/embed.py with a made-up embed function: no fastembed, no download."""
import numpy as np
import pytest

from src.embed import embed_items

ITEMS = [
    {"n": 1, "text": "water the ferns"},
    {"n": 2, "text": "renew the library card"},
    {"n": 3, "text": "oil the gate hinge"},
]


def fake_embed(texts):
    return np.array([[len(t), t.count("e") + 1, 2.0] for t in texts])


def test_one_unit_vector_per_item_in_order():
    vectors = embed_items(ITEMS, fake_embed)
    assert vectors.shape == (3, 3)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    raw = fake_embed([it["text"] for it in ITEMS])
    assert np.allclose(vectors, raw / np.linalg.norm(raw, axis=1, keepdims=True), atol=1e-6)


def test_blank_item_is_an_error_not_a_skip():
    with pytest.raises(ValueError, match="1 items have no text"):
        embed_items(ITEMS + [{"n": 4, "text": "  "}], fake_embed)


def test_wrong_number_of_vectors_is_an_error():
    with pytest.raises(ValueError, match="3 items in"):
        embed_items(ITEMS, lambda texts: fake_embed(texts)[:2])


def test_zero_vector_is_an_error():
    with pytest.raises(ValueError, match="zero vectors"):
        embed_items(ITEMS, lambda texts: np.zeros((len(texts), 3)))
