"""Tests for the expression registry ('hopper_expr_register') and hopper_max_idx."""

import polars as pl


def test_hopper_max_idx_initialization():
    """Ensures the plugin sets hopper_max_idx to -1 if it is absent.

    Then increments it by the count of newly added expressions.
    """
    df = pl.DataFrame({"col": [1, 2, 3]})

    # Check that 'hopper_max_idx' is unset initially
    meta = df.config_meta.get_metadata()
    assert (
        "hopper_max_idx" not in meta
    ), "Expected hopper_max_idx not to exist before plugin init."

    # Trigger plugin init
    df.hopper
    meta_post_init = df.config_meta.get_metadata()
    # Our code sets hopper_max_idx to -1 only when we actually add exprs,
    # so if the plugin doesn't set it on init, we confirm it is still absent or unchanged.
    assert (
        "hopper_max_idx" not in meta_post_init
    ), "hopper_max_idx is set only on first add_exprs call."

    # Now add 2 expressions
    df.hopper.add_filters(pl.col("col") > 1, pl.col("col") < 3)
    meta_after_add = df.config_meta.get_metadata()

    # The code sets hopper_max_idx = -1 if not present, then increments by len(exprs).
    #  -> started at -1, plus 2 => final is 1
    assert (
        meta_after_add["hopper_max_idx"] == 1
    ), "hopper_max_idx should start at -1, then increment by 2 to 1."

    # Add 1 more expression
    df.hopper.add_selects(pl.col("col") * 2)
    meta_after_second_add = df.config_meta.get_metadata()
    # hopper_max_idx was 1, plus 1 new expression => becomes 2
    assert (
        meta_after_second_add["hopper_max_idx"] == 2
    ), "hopper_max_idx should now be 2 after adding one more expression."


def test_hopper_max_idx_increments_existing():
    """Verifies hopper_max_idx increments by the number of expressions added.

    (When the key is already present)
    """
    df = pl.DataFrame({"val": [10, 20]})
    df.config_meta.set(hopper_max_idx=5)  # Suppose we already have a value of 5

    # Confirm the plugin doesn't overwrite this key on init
    df.hopper
    meta_init = df.config_meta.get_metadata()
    assert (
        meta_init["hopper_max_idx"] == 5
    ), "The plugin shall preserve the existing hopper_max_idx."

    # Add 3 expressions
    df.hopper.add_addcols(
        (pl.col("val") + 10).alias("val_plus_10"),
        (pl.col("val") * 2).alias("val_x2"),
        (pl.col("val") - 5).alias("val_minus_5"),
    )
    meta_after_add = df.config_meta.get_metadata()

    # The old value was 5, plus 3 expressions => 8
    assert (
        meta_after_add["hopper_max_idx"] == 8
    ), "hopper_max_idx should increase from 5 to 8 after adding 3 expressions."

    # Add 2 more expressions of any kind
    df.hopper.add_filters(pl.col("val") > 15, pl.col("val") < 25)
    meta_after_more = df.config_meta.get_metadata()

    # The old value was 8, plus 2 expressions => 10
    assert (
        meta_after_more["hopper_max_idx"] == 10
    ), "hopper_max_idx should now be 10 after adding 2 more expressions."


def test_expr_registry_creation_and_schema():
    """Verify that adding expressions creates 'hopper_expr_register' NDJSON in metadata.

    Correct schema columns: idx, kind, expr, applied, root_names.
    """
    df = pl.DataFrame({"num": [1, 2, 3]})
    meta_before = df.config_meta.get_metadata()
    # Confirm that 'hopper_expr_register' is not present at the start
    assert (
        "hopper_expr_register" not in meta_before
    ), "Registry should not exist initially."

    df.hopper
    meta_mid = df.config_meta.get_metadata()
    # Confirm that we still do not have 'hopper_expr_register' until we add exprs
    assert (
        "hopper_expr_register" not in meta_mid
    ), "No register until expressions are actually added."

    # Add a single filter expression
    df.hopper.add_filters(pl.col("num") > 1)
    meta_after_add = df.config_meta.get_metadata()
    # Now 'hopper_expr_register' must exist
    assert (
        "hopper_expr_register" in meta_after_add
    ), "Registry should be created upon first addition."

    ndjson_str = meta_after_add["hopper_expr_register"]
    reg_df = pl.read_ndjson(ndjson_str.encode())

    # Confirm the columns
    expected_cols = {"idx", "kind", "expr", "applied", "root_names"}
    assert (
        set(reg_df.columns) == expected_cols
    ), "Registry must have the correct schema columns."
    # We have exactly 1 row
    assert reg_df.shape == (1, 5)
    row = reg_df.to_dicts()[0]
    assert (
        row["idx"] == 0
    ), "First expression should have idx=0 (hopper_max_idx started at -1)."
    assert row["kind"] == "f", "We added a filter, so kind should be 'f'."
    assert not row["applied"], "Newly added expressions are not yet applied."
    # 'expr' is the JSON-serialized expression string
    assert (
        isinstance(row["expr"], str) and row["expr"]
    ), "Must store expression as a nonempty JSON string."
    # 'root_names' must reflect the columns the expression references
    assert row["root_names"] == ["num"], "Should detect the 'num' column as root name."


def test_expr_registry_multiple_additions_kinds_and_max_idx():
    """Adding multiple expressions of different kinds increments hopper_max_idx.

    Also appends registry rows for each new expression with correct 'kind'.
    """
    df = pl.DataFrame({"foo": [10, 20], "bar": [1, 2]})
    # Force an initial hopper_max_idx
    df.config_meta.set(hopper_max_idx=5)
    df.hopper  # init

    # Add 2 filters
    df.hopper.add_filters(pl.col("foo") > 0, pl.col("bar") > 0)  # idx=6,7
    # Add 1 select
    df.hopper.add_selects(pl.col("foo"), pl.col("bar"))  # idx=8,9
    # Add 1 addcols
    df.hopper.add_addcols((pl.col("bar") + 1).alias("bar_plus_1"))  # idx=10

    meta = df.config_meta.get_metadata()
    assert (
        meta["hopper_max_idx"] == 10
    ), "Max idx started at 5, plus 4 expressions => 9, plus 1 => 10."

    # Parse the registry
    ndjson_str = meta["hopper_expr_register"]
    reg_df = pl.read_ndjson(ndjson_str.encode())
    # We added 2 filter, 2 select, 1 addcols => total 5 new rows
    assert reg_df.shape == (5, 5), "We should have 5 total expressions in the registry."

    # Sort by idx to see them in ascending order
    reg_sorted = reg_df.sort("idx")
    all_kinds = reg_sorted["kind"].to_list()
    # Expect the order: f, f, s, s, a
    assert all_kinds == [
        "f",
        "f",
        "s",
        "s",
        "a",
    ], f"Got unexpected kinds in {all_kinds}"

    # Confirm idx values go from 6..10
    idx_vals = reg_sorted["idx"].to_list()
    assert idx_vals == [6, 7, 8, 9, 10], f"Indices must be 6..10 but got {idx_vals}"

    # All newly added expressions remain 'applied=False'
    applied_vals = reg_sorted["applied"].to_list()
    assert all(not val for val in applied_vals), "None of these have been applied yet."


def test_expr_registry_root_names_for_various_exprs():
    """Registry 'root_names' is accurate to referenced columns from each expresstion."""
    df = pl.DataFrame({"a": [5], "b": [10], "c": [15]})
    df.hopper.add_filters(
        pl.col("a") > 2,
        pl.col("b") + pl.col("c") < 100,
    )
    df.hopper.add_selects(
        (pl.col("a") + pl.col("b")),
    )
    df.hopper.add_addcols(
        (pl.col("c") * 2).alias("c_times_2"),
    )

    meta = df.config_meta.get_metadata()
    ndjson_str = meta["hopper_expr_register"]
    reg_df = pl.read_ndjson(ndjson_str.encode())
    assert reg_df.shape == (4, 5), "We added 4 expressions total."

    # We'll map the 'expr' to the 'root_names' in the registry
    # Because .sort() might reorder them, let's just examine them in the order added
    # We'll rely on idx ascending or parse them directly from the partial data we have
    data_rows = reg_df.sort("idx").to_dicts()

    # We expect 2 filters, 1 select, 1 addcols => total 4
    # Let's check each row's root_names
    # row0 => pl.col("a") > 2 => root_names=["a"]
    # row1 => pl.col("b") + pl.col("c") < 100 => root_names=["b","c"]
    # row2 => (pl.col("a") + pl.col("b")) => root_names=["a","b"]
    # row3 => (pl.col("c") *2).alias("c_times_2") => root_names=["c"]

    row0 = data_rows[0]
    assert row0["root_names"] == [
        "a",
    ], f"Expected only 'a' in row0, got {row0['root_names']}"
    row1 = data_rows[1]
    assert set(row1["root_names"]) == {
        "b",
        "c",
    }, f"Expected b,c in row1, got {row1['root_names']}"
    row2 = data_rows[2]
    assert set(row2["root_names"]) == {
        "a",
        "b",
    }, f"Expected a,b in row2, got {row2['root_names']}"
    row3 = data_rows[3]
    assert row3["root_names"] == ["c"], f"Expected c in row3, got {row3['root_names']}"

    # Also confirm all are still not applied
    for r in data_rows:
        assert not r[
            "applied"
        ], "No expressions have been applied yet, so 'applied' is false."
