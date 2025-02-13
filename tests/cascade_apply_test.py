import polars as pl


def test_cascade_addcols_and_filter():
    """
    Demonstrate "cascading" apply:
      1) Add 'is_amazon' column from 'description',
      2) Then immediately filter on 'is_amazon',
      3) All in a single call to df.hopper.apply_ready_exprs().
    """
    # Start with a DataFrame that has a column "description" but no "is_amazon".
    df = pl.DataFrame(
        {
            "description": [
                "some text about AWS",
                "some text about GCP",
                "yet more text about AWS",
            ]
        }
    )

    # 1) Add an addcols expression that references the existing column "description"
    df.hopper.add_addcols(pl.col("description").str.contains("AWS").alias("is_amazon"))

    # 2) Add a filter expression referencing "is_amazon", which doesn't yet exist
    df.hopper.add_filters(pl.col("is_amazon"))

    # 3) Apply all expressions in one go. We expect the addcols to apply first,
    #    so that "is_amazon" is created, then the filter referencing that new
    #    column will also apply.
    df2 = df.hopper.apply_ready_exprs()  # effectively apply_ready_addcols + apply_ready_filters

    # Check final shape: 
    # We expect 2 rows (both referencing AWS) and 2 columns: [description, is_amazon].
    assert df2.shape == (2, 2), (
        "Expected to see only the rows containing 'AWS' and columns 'description' + 'is_amazon'. "
        f"Got shape: {df2.shape}"
    )

    # Optionally, check final column values.
    # We expect:
    #   description = ["some text about AWS", "yet more text about AWS"]
    #   is_amazon   = [True, True]
    assert df2["is_amazon"].to_list() == [True, True], "Should have filtered out non-AWS rows."

    # Check that the plugin’s registry is empty or at least that the *filter* is removed,
    # depending on how you handle addcols (some code removes them once applied; some code does not).
    reg2 = df2.hopper._read_expr_registry()
    assert reg2.shape[0] == 0, f"Registry should be empty after successful cascade.\n{reg2}"
    
    # Or, if your code doesn't pop addcols, check that it only has the addcols left (but not the filter).
    # e.g.:
    # filter_remaining = reg2.filter(pl.col("kind") == "f")
    # assert filter_remaining.is_empty(), "Filter should have been removed from registry"
