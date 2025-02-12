"""Tests for storing filter expressions on DataFrame creation (RQ1)."""

import polars as pl


def test_store_filters():
    """PRD RQ1: The plugin shall store each filter expression in df.config_meta['hopper_filters']."""
    df = pl.DataFrame({"x": [1, 2, 3]})

    meta = df.config_meta.get_metadata()
    assert meta.get("hopper_filters", []) == []

    df.hopper.add_filters(pl.col("x") > 1)

    meta_after = df.config_meta.get_metadata()
    stored = meta_after.get("hopper_filters", [])
    assert len(stored) == 1, "Expected exactly 1 filter in the hopper."
