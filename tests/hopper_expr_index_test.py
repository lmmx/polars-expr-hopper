"""Tests for the new monotonically increasing hopper_max_idx (commit bcf52fd...)."""

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
