"""Tests for the 'select' functionality of the Polars hopper plugin (RQ6–RQ10)."""

import polars as pl


def test_store_selects():
    """RQ6.

    The plugin shall store Polars select expressions in 'hopper_selects'
    whenever the user calls df.hopper.add_selects(...).
    """
    df = pl.DataFrame({"id": [1, 2, 3], "val": [10, 20, 30]})
    meta_before = df.config_meta.get_metadata()
    assert meta_before.get("hopper_selects") is None, "hopper_selects should be unset."
    df.hopper  # Any reference initialises the namespace
    meta_mid = df.config_meta.get_metadata()
    assert meta_mid.get("hopper_selects") == [], "hopper_selects should start empty."

    # Add a select expression
    df.hopper.add_selects(pl.col("id"), pl.col("val") * 2)
    meta_after = df.config_meta.get_metadata()
    selects_stored = meta_after.get("hopper_selects", [])
    assert len(selects_stored) == 2, "Expected 2 select expressions stored."


def test_apply_ready_selects_complete():
    """RQ7 + RQ10.

    - The plugin shall apply each stored select expression only
      when all referenced columns exist, removing it on success.
    - The resulting DataFrame shall contain only columns
      produced by the applied select expressions.
    """
    df = pl.DataFrame({"x": [10, 20, 30], "y": [1, 2, 3]})
    # Add a select expression referencing existing columns
    df.hopper.add_selects(pl.col("x"), pl.col("y") + 100)

    # Apply
    df_selected = df.hopper.apply_ready_selects()
    # Because we can apply both expressions in turn,
    # the new DataFrame should have only columns from the final select
    # The first select is pl.col("x"), the second (and final) is pl.col("y") + 100
    # Each is applied in sequence, so the final DataFrame is from
    # the second expression.
    # Note that after the first .select(...) we lose 'y' unless the second
    # expression's columns exist in that new shape.
    # In polars, the second expression can't succeed if the first select
    # stripped out 'y'. Let's confirm the logic or store multiple expressions
    # in a single pass.

    # In the default plugin code, it attempts the first expression =>
    #    new_df = df.select(pl.col("x"))
    # next expression => that new_df only has 'x', so "y" does not exist => skip
    # So effectively we expect the final DataFrame has columns ["x"],
    # and the second expression is still pending in hopper_selects.
    # This is normal due to the sequence each expression is tried in.

    assert df_selected.columns == [
        "x",
    ], "Only 'x' should be present after the first successful select."
    meta_after = df_selected.config_meta.get_metadata()
    still_pending = meta_after.get("hopper_selects", [])
    assert (
        len(still_pending) == 1
    ), "The second select expression referencing 'y' should remain pending."


def test_apply_ready_selects_with_missing_cols():
    """RQ7.

    The plugin shall not apply a select expression if its referenced columns
    do not exist, leaving that expression pending.
    """
    df = pl.DataFrame({"a": [5, 6, 7]})
    # Add a select expression that references a missing column 'b'
    df.hopper.add_selects(pl.col("a"), pl.col("b"))

    # Apply: only the first expression is valid.
    # The second expression references 'b' and must remain pending.
    df2 = df.hopper.apply_ready_selects()
    assert df2.shape == (3, 1), "Applying the first select yields one column 'a'."
    assert df2.columns == ["a"], "Only 'a' is present."

    meta2 = df2.config_meta.get_metadata()
    pending_exprs = meta2.get("hopper_selects", [])
    assert len(pending_exprs) == 1, "One select expression remains pending."

    # Introduce column 'b'
    df3 = df2.hopper.with_columns(pl.Series("b", [50, 60, 70]))
    df4 = df3.hopper.apply_ready_selects()
    # Now the second expression referencing 'b' can apply,
    # but notice that df3 only has columns 'a' and 'b' =>
    # after applying the second expression, the final DataFrame
    # should have only the columns from that expression, i.e. 'b'.
    assert df4.columns == ["b"], "After successful second select, only 'b' remains."

    meta4 = df4.config_meta.get_metadata()
    assert (
        len(meta4.get("hopper_selects", [])) == 0
    ), "No pending selects remain after success."


def test_preservation_selects():
    """RQ8.

    The plugin shall preserve 'hopper_selects' metadata across DataFrame
    transformations (like .select or .with_columns) unless the expressions
    have been applied or removed.
    """
    df = pl.DataFrame({"u": [1, 2], "v": [10, 20]})
    df.hopper.add_selects(pl.col("u") * 2, pl.col("v") - 5)

    # Transform with .with_columns(...) to see if metadata is preserved.
    df2 = df.hopper.with_columns((pl.col("v") * 10).alias("v_times_10"))
    meta2 = df2.config_meta.get_metadata()
    # The original 'hopper_selects' should still be present
    stored_selects = meta2.get("hopper_selects", [])
    assert (
        len(stored_selects) == 2
    ), "Select expressions are preserved across transformations."

    # Now apply them
    df3 = df2.hopper.apply_ready_selects()
    assert df3.columns == ["u"], "After applying the first select, only 'u' remains."
    assert (
        len(df3.config_meta.get_metadata().get("hopper_selects", [])) == 1
    ), "One select expression should remain if 'v' is lost after the first select."


def test_multiple_selects_sequence():
    """RQ9.

    The plugin shall apply multiple select expressions in sequence
    if all referenced columns exist for each expression, leaving incomplete
    expressions for future runs.
    """
    df = pl.DataFrame({"col1": [100, 200], "col2": [10, 20], "col3": [1, 2]})
    # We add three expressions:
    #  1) pl.col("col1") -> can apply immediately
    #  2) pl.col("col2") + 5 -> references col2
    #  3) pl.col("col1") + pl.col("col3") -> references col1 & col3
    #     but 'col1' is lost after the first select
    df.hopper.add_selects(
        pl.col("col1"),
        (pl.col("col2") + 5).alias("col2_plus_5"),
        (pl.col("col1") + pl.col("col3")).alias("sum_col1_col3"),
    )

    df2 = df.hopper.apply_ready_selects()
    # 1) The first expression can apply => new df = df.select(pl.col("col1")) => columns=["col1"]
    # 2) The second expression references "col2", missing => remains pending
    # 3) The third references "col1" & "col3" => col3 missing => remains pending
    assert df2.columns == ["col1"], "Applied the first select that references col1."
    meta2 = df2.config_meta.get_metadata()
    left_pending = meta2.get("hopper_selects", [])
    assert len(left_pending) == 2, "The second and third expressions remain pending."

    # Now let's re-introduce col2 & col3 by adding them back
    df3 = df2.hopper.with_columns(
        pl.Series("col2", [10, 20]),
        pl.Series("col3", [1, 2]),
    )
    df4 = df3.hopper.apply_ready_selects()
    # Now the second expression needs "col2" => valid => new df => columns=["col2_plus_5"]
    # The third expression needs "col1" & "col3", but the new df from the second select has only ["col2_plus_5"]
    # so the third expression remains pending again.
    assert df4.columns == [
        "col2_plus_5",
    ], "After the second select, only 'col2_plus_5' remains."
    meta4 = df4.config_meta.get_metadata()
    still_pending = meta4.get("hopper_selects", [])
    assert (
        len(still_pending) == 1
    ), "The third expression referencing 'col1' & 'col3' is still pending."

    # Finally, let's re-introduce 'col1' & 'col3'
    df5 = df4.hopper.with_columns(
        pl.Series("col1", [100, 200]),
        pl.Series("col3", [1, 2]),
    )
    df6 = df5.hopper.apply_ready_selects()
    # Now the third expression can apply => new df => columns=["sum_col1_col3"]
    assert df6.columns == [
        "sum_col1_col3",
    ], "Final expression is applied, referencing col1 and col3."
    meta6 = df6.config_meta.get_metadata()
    assert len(meta6.get("hopper_selects", [])) == 0, "No pending selects remain."


def test_selects_metadata_merge():
    """RQ10.

    The plugin shall produce the resulting DataFrame containing only columns
    from successfully applied select expressions, with updated 'hopper_selects'
    metadata that removes the applied expressions.
    """
    df = pl.DataFrame({"alpha": [1, 2, 3], "beta": [10, 20, 30]})
    df.hopper.add_selects(
        (pl.col("alpha") * 10).alias("alpha_x10"),
        (pl.col("beta") + 1).alias("beta_plus1"),
    )

    df2 = df.hopper.apply_ready_selects()
    # Because the plugin processes them in order:
    # - After the first expression, the DataFrame has a single column "alpha_x10"
    # - The second expression references "beta," which no longer exists
    #   in the newly selected DataFrame => remains pending
    assert df2.columns == ["alpha_x10"]
    meta2 = df2.config_meta.get_metadata()
    pending_after_first = meta2.get("hopper_selects", [])
    assert (
        len(pending_after_first) == 1
    ), "The second expression referencing 'beta' remains."

    # Introduce 'beta' again
    df3 = df2.hopper.with_columns(pl.Series("beta", [10, 20, 30]))
    df4 = df3.hopper.apply_ready_selects()
    # Now the second expression can apply, referencing 'beta'.
    # The new DataFrame has only "beta_plus1"
    assert df4.columns == ["beta_plus1"]
    meta4 = df4.config_meta.get_metadata()
    assert (
        len(meta4.get("hopper_selects", [])) == 0
    ), "All select expressions are applied, none remain."
