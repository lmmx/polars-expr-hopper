import polars as pl


def test_store_filters():
    """PRD RQ1: The polars-filter-hopper plugin shall store each filter expression
    in df.config_meta['hopper_filters'] at addition.
    """
    df = pl.DataFrame({"x": [1, 2, 3]})

    # Confirm 'hopper_filters' is initially empty
    meta = df.config_meta.get_metadata()
    assert meta.get("hopper_filters", []) == []

    # Add a filter
    df.hopper.add_filter(lambda df_: pl.col("x") > 1)

    # Check stored filters
    meta_after = df.config_meta.get_metadata()
    stored = meta_after.get("hopper_filters", [])
    assert len(stored) == 1, "Expected exactly 1 filter in the hopper."
