"""Tests for the 'with_columns' ('addcols') functionality of the Polars hopper plugin.

We verify that 'addcols' expressions are stored, preserved, and applied only
when their referenced columns exist, mirroring the behavior of 'select' but
for DataFrame column additions/overwrites.
"""

import polars as pl


def test_store_addcols():
    """Check that 'hopper_addcols' is created when needed and stores new expressions."""
    df = pl.DataFrame({"foo": [1, 2, 3]})
    meta_before = df.config_meta.get_metadata()

    # Initially 'hopper_addcols' should be None or absent
    assert (
        meta_before.get("hopper_addcols") is None
    ), "hopper_addcols should be unset before first use."

    # Trigger the hopper plugin init
    df.hopper
    meta_mid = df.config_meta.get_metadata()
    assert (
        meta_mid.get("hopper_addcols") == []
    ), "hopper_addcols should start as an empty list."

    # Add new addcols expressions
    df.hopper.add_addcols(pl.col("foo") * 10, pl.col("foo") + 5)
    meta_after = df.config_meta.get_metadata()
    stored_addcols = meta_after.get("hopper_addcols", [])
    assert len(stored_addcols) == 2, "Expected 2 addcols expressions to be stored."


def test_apply_ready_addcols_when_all_cols_exist():
    """Apply addcols expressions when their referenced columns already exist."""
    df = pl.DataFrame({"a": [10, 20], "b": [100, 200]})
    # We add expressions that reference 'a' and 'b', which both exist
    df.hopper.add_addcols(
        (pl.col("a") + 1).alias("a_plus_1"),
        (pl.col("b") * 2).alias("b_times_2"),
    )

    df2 = df.hopper.apply_ready_addcols()
    # Because with_columns(...) retains existing columns, the new DataFrame
    # should have the original 'a', 'b', plus the newly added columns.
    assert set(df2.collect_schema().keys()) == {"a", "b", "a_plus_1", "b_times_2"}, (
        "All expressions apply because 'a' and 'b' exist, "
        "and the resulting DF gains the new columns."
    )
    meta2 = df2.config_meta.get_metadata()
    assert (
        meta2.get("hopper_addcols", []) == []
    ), "No expressions remain pending after successful application."


def test_apply_ready_addcols_missing_cols():
    """Expressions that reference missing columns should remain pending.

    Others that reference existing columns should apply immediately.
    """
    df = pl.DataFrame({"x": [1, 2, 3]})
    df.hopper.add_addcols(
        (pl.col("x") * 2).alias("x_times_2"),  # references 'x' -> valid now
        (pl.col("y") + 100).alias("y_plus_100"),  # references 'y' -> missing
    )

    df2 = df.hopper.apply_ready_addcols()
    # The first expression applies, the second remains pending
    assert set(df2.collect_schema().keys()) == {
        "x",
        "x_times_2",
    }, "First addcols was successful, second still pending."
    meta2 = df2.config_meta.get_metadata()
    pending_exprs = meta2.get("hopper_addcols", [])
    assert len(pending_exprs) == 1, "One expression remains (references missing 'y')."

    # Now we introduce 'y'
    df3 = df2.hopper.with_columns(pl.Series("y", [10, 20, 30]))
    df4 = df3.hopper.apply_ready_addcols()
    # That pending expression can now apply
    expected_cols = {"x", "x_times_2", "y", "y_plus_100"}
    assert (
        set(df4.collect_schema().keys()) == expected_cols
    ), "All columns plus 'y_plus_100' after second expression applies."
    assert not df4.config_meta.get_metadata().get(
        "hopper_addcols",
    ), "No pending addcols remain."


def test_preservation_addcols():
    """Verify 'hopper_addcols' metadata remains intact across DataFrame transformations.

    Unless those expressions have been applied.
    """
    df = pl.DataFrame({"foo": [3, 4], "bar": [30, 40]})
    df.hopper.add_addcols(
        (pl.col("foo") * 10).alias("foo_x10"),
        (pl.col("bar") - 1).alias("bar_minus_1"),
    )

    # Transform with a separate call to with_columns to see if metadata is preserved
    df2 = df.hopper.with_columns((pl.col("bar") + 100).alias("bar_plus_100"))
    meta2 = df2.config_meta.get_metadata()
    pending_addcols = meta2.get("hopper_addcols", [])
    assert (
        len(pending_addcols) == 2
    ), "All addcols expressions are preserved after with_columns() call."

    # Apply them now
    df3 = df2.hopper.apply_ready_addcols()
    # with_columns retains existing columns, so the first expression referencing 'foo' can apply,
    # the second referencing 'bar' can apply. Both should succeed => new columns appear.
    # Original columns remain too.
    all_cols = {"foo", "bar", "bar_plus_100", "foo_x10", "bar_minus_1"}
    assert set(df3.columns) == all_cols
    # But note that "bar_plus_100" was added in the prior step as a single expression,
    # so the final DF has it. Check for presence:
    df3_cols = set(df3.collect_schema().keys())
    for col in ["foo", "bar", "foo_x10", "bar_minus_1"]:
        assert col in df3_cols
    # "bar_plus_100" only appears if you used an alias. Let's see: we didn't alias it, so Polars
    # typically names it "literal" or something. For simplicity, let's not check it strictly.
    # The key point: the 2 stored addcols were applied => none remain.
    meta3 = df3.config_meta.get_metadata()
    assert not meta3.get(
        "hopper_addcols",
    ), "All addcols expressions applied, none remain."


def test_multiple_addcols_sequence():
    """The plugin shall apply multiple addcols expressions in sequence.

    If references are missing, those expressions remain pending;
    after we introduce the needed columns, we can re-apply.
    """
    df = pl.DataFrame({"a": [1, 2, 3]})
    # Three expressions:
    # (1) pl.col("a") + 1 -> can apply immediately
    # (2) pl.col("b") * 2 -> missing 'b'
    # (3) pl.col("a") + pl.col("c") -> missing 'c'
    df.hopper.add_addcols(
        (pl.col("a") + 1).alias("a_plus_1"),
        (pl.col("b") * 2).alias("b_times_2"),
        (pl.col("a") + pl.col("c")).alias("a_plus_c"),
    )

    df2 = df.hopper.apply_ready_addcols()
    # (1) applies => "a_plus_1" is created. (2) and (3) remain pending
    assert set(df2.collect_schema().keys()) == {
        "a",
        "a_plus_1",
    }, "First addcols applied."
    meta2 = df2.config_meta.get_metadata()
    assert len(meta2.get("hopper_addcols", [])) == 2, "Two expressions still pending."

    # Introduce 'b'
    df3 = df2.hopper.with_columns(pl.Series("b", [10, 20, 30]))
    df4 = df3.hopper.apply_ready_addcols()
    # (2) can now apply, adding "b_times_2"
    # (3) still references 'c', so remains pending
    expected_cols = {"a", "a_plus_1", "b", "b_times_2"}
    assert set(df4.collect_schema().keys()) == expected_cols, "Second addcols applied."
    meta4 = df4.config_meta.get_metadata()
    assert (
        len(meta4.get("hopper_addcols", [])) == 1
    ), "Still one expression referencing 'c' pending."

    # Finally, introduce 'c'
    df5 = df4.hopper.with_columns(pl.Series("c", [100, 200, 300]))
    df6 = df5.hopper.apply_ready_addcols()
    # (3) can now apply => adds "a_plus_c"
    all_expected = {"a", "a_plus_1", "b", "b_times_2", "c", "a_plus_c"}
    assert (
        set(df6.collect_schema().keys()) == all_expected
    ), "All addcols eventually applied."
    assert not df6.config_meta.get_metadata().get(
        "hopper_addcols",
    ), "No pending expressions remain."


def test_addcols_metadata_merge():
    """The plugin shall produce a resulting DataFrame with newly added columns.

    Removing successfully applied addcols expressions from metadata.
    """
    df = pl.DataFrame({"alpha": [100, 200], "beta": [1, 2]})
    df.hopper.add_addcols(
        (pl.col("alpha") / 10).alias("alpha_div_10"),
        (pl.col("gamma") + 3).alias("gamma_plus_3"),
    )
    # Only the first expression references existing columns => 'gamma' missing
    df2 = df.hopper.apply_ready_addcols()
    assert set(df2.collect_schema().keys()) == {
        "alpha",
        "beta",
        "alpha_div_10",
    }, "First expression applied. 'gamma_plus_3' still pending."
    meta2 = df2.config_meta.get_metadata()
    pending = meta2.get("hopper_addcols", [])
    assert len(pending) == 1, "Missing 'gamma' => second expression remains pending."

    # Introduce 'gamma'
    df3 = df2.hopper.with_columns(pl.Series("gamma", [10, 20]))
    df4 = df3.hopper.apply_ready_addcols()
    # Now the second expression can apply
    assert set(df4.collect_schema().keys()) == {
        "alpha",
        "beta",
        "alpha_div_10",
        "gamma",
        "gamma_plus_3",
    }, "Successfully applied 'gamma_plus_3'."
    meta4 = df4.config_meta.get_metadata()
    assert not meta4.get("hopper_addcols"), "No pending addcols remain."
