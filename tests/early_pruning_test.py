import polars as pl


def test_early_pruning():
    """PRD RQ5: The plugin removes rows as soon as columns appear."""
    df = pl.DataFrame({"repo_is_fork": [False, True, True, False]})
    # Create the hopper_filters list
    df.config_meta.set(hopper_filters=[lambda df_: pl.col("repo_is_fork") == False])

    df2 = df.hopper.apply_ready_filters()
    assert df2.shape == (2, 1), "Should remove rows with repo_is_fork==True."

    # Add a new filter referencing 'stars'
    meta2 = df2.config_meta.get_metadata()
    pending = meta2.get("hopper_filters", [])
    pending.append(lambda df_: pl.col("stars") > 50)
    meta2["hopper_filters"] = pending
    df2.config_meta.set(**meta2)

    df3 = df2.hopper.apply_ready_filters()
    assert df3.shape == (2, 1), "No change yet, 'stars' missing."

    # Now introduce stars
    df4 = df3.hopper.with_columns(pl.Series("stars", [100, 30]))
    df5 = df4.hopper.apply_ready_filters()
    assert df5.shape == (1, 2), "stars<=50 removed."
    meta5 = df5.config_meta.get_metadata()
    assert len(meta5["hopper_filters"]) == 0, "Filter cleared after success."
