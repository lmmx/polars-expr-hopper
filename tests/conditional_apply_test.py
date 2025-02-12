"""Tests for conditional filter application (RQ2)."""

import polars as pl


def test_conditional_apply():
    """PRD RQ2: The plugin applies filters only if columns exist, then removes them on success."""
    df = pl.DataFrame({"user_id": [0, 1, 2]})
    # Add a filter referencing age
    df.hopper.add_filters(pl.col("age") > 18)

    # Apply
    df2 = df.hopper.apply_ready_filters()
    assert df2.shape == (3, 1)
    meta = df2.config_meta.get_metadata()
    assert len(meta["hopper_filters"]) == 1, "Filter remains pending."

    # Introduce 'age'
    df3 = df2.hopper.with_columns(pl.Series("age", [25, 15, 30]))
    df4 = df3.hopper.apply_ready_filters()
    assert df4.shape == (2, 2), "Age<=18 removed."
    meta4 = df4.config_meta.get_metadata()
    assert len(meta4["hopper_filters"]) == 0, "Filter removed after application."
