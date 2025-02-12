import polars as pl


def test_metadata_preservation():
    """PRD RQ3: The plugin preserves hopper_filters across transformations if
    called via df.config_meta.* methods.
    """
    df = pl.DataFrame({"idx": [10, 20, 30]})
    # Set 'hopper_filters' directly with config_meta
    df.config_meta.set(hopper_filters=[lambda df_: pl.col("idx") < 25])

    df2 = df.config_meta.select(pl.col("idx"))

    meta2 = df2.config_meta.get_metadata()
    assert "hopper_filters" in meta2, "hopper_filters key must exist."
    assert len(meta2["hopper_filters"]) == 1, "Should preserve the filter."

    # Apply the filter
    df3 = df2.hopper.apply_ready_filters()
    assert df3.shape == (2, 1), "Rows with idx>=25 removed."
