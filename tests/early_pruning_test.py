"""Tests for early pruning of rows when columns become available (RQ5)."""

import polars as pl


def test_early_pruning():
    """PRD RQ5: The plugin removes rows as soon as columns appear, preventing waste."""
    df = pl.DataFrame({"repo_is_fork": [False, True, True, False]})
    # Use .eq(False) instead of == False
    df.hopper.add_filters(pl.col("repo_is_fork").eq(False))

    df2 = df.hopper.apply_ready_filters()
    assert df2.shape == (2, 1), "Should remove rows with repo_is_fork==True."

    # Add a new filter referencing 'stars'
    meta2 = df2.config_meta.get_metadata()
    pending = meta2.get("hopper_filters")
    assert pending == []
    df2.hopper.add_filters(pl.col("stars") > 50)
    meta2_post = df2.config_meta.get_metadata()
    pending_post = meta2_post.get("hopper_filters")
    assert len(pending_post) == 1

    df3 = df2.hopper.apply_ready_filters()
    assert df3.shape == (2, 1), "No change yet, 'stars' missing."

    # Now introduce stars
    df4 = df3.hopper.with_columns(pl.Series("stars", [100, 30]))
    df5 = df4.hopper.apply_ready_filters()
    assert df5.shape == (1, 2), "stars<=50 removed."
    meta5 = df5.config_meta.get_metadata()
    assert len(meta5["hopper_filters"]) == 0, "Filter cleared after success."
