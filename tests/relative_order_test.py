"""Test the effect of relative order of exprs."""

import polars as pl


def test_order_dependency_bug():
    """Add the same expressions in different orders.

    We'll do two scenarios:
      A) Filter(s) referencing 'is_amazon' before we addcols 'is_amazon'
      B) Addcols 'is_amazon' before we add the filter(s)
    """
    # -------------------------------------------------------------------------
    # Scenario A: filters referencing "is_amazon" ADDED BEFORE the addcols
    # -------------------------------------------------------------------------
    dfA = pl.DataFrame(
        {
            "description": [
                "some text about AWS",
                "some text about GCP",
                "boto3 references for AWS",
                "completely unrelated",
            ],
        },
    )

    # 1) Add a filter referencing "is_amazon" (which doesn't exist yet)
    dfA.hopper.add_filters(pl.col("is_amazon"))

    # 2) Add one more filter referencing "is_amazon", to simulate your CLI example
    dfA.hopper.add_filters(pl.col("is_amazon"))

    # 3) Now add the addcols that actually creates "is_amazon"
    dfA.hopper.add_addcols(pl.col("description").str.contains("AWS").alias("is_amazon"))

    # 4) Apply everything in "one go" (the new code presumably does multi-pass)
    dfA2 = dfA.hopper.apply_ready_exprs()

    # Check final shape
    # Rows referencing AWS remain, and we've filtered out the GCP/unrelated line
    assert dfA2.shape == (2, 2), f"Scenario A shape mismatch: {dfA2.shape}"
    # Check registry is empty or at least doesn't show duplicates
    regA2 = dfA2.hopper._read_expr_registry()
    # We'll just store for logging, see after we do scenario B
    print("Scenario A final registry:", regA2)

    # -------------------------------------------------------------------------
    # Scenario B: addcols FIRST, then filters referencing "is_amazon"
    # -------------------------------------------------------------------------
    dfB = pl.DataFrame(
        {
            "description": [
                "some text about AWS",
                "some text about GCP",
                "boto3 references for AWS",
                "completely unrelated",
            ],
        },
    )

    # 1) Add the addcols that creates "is_amazon"
    dfB.hopper.add_addcols(pl.col("description").str.contains("AWS").alias("is_amazon"))

    # 2) Add the same two filters referencing "is_amazon"
    dfB.hopper.add_filters(pl.col("is_amazon"))
    dfB.hopper.add_filters(pl.col("is_amazon"))

    # 3) Apply all
    dfB2 = dfB.hopper.apply_ready_exprs()

    # Same final shape check
    assert dfB2.shape == (2, 2), f"Scenario B shape mismatch: {dfB2.shape}"
    # Check final registry
    regB2 = dfB2.hopper._read_expr_registry()
    print("Scenario B final registry:", regB2)

    # -------------------------------------------------------------------------
    # Compare registry or shape
    # -------------------------------------------------------------------------
    # Typically we expect both final dataframes to look the same. But if your
    # plugin is order-dependent, you'll see differences in how many times the
    # filter expressions were popped, or if they're duplicated, etc.
    #
    # Here's an optional test to confirm the registry is empty (or at least
    # the same) in both scenarios:
    # -------------------------------------------------------------------------
    assert (
        regA2.shape == regB2.shape
    ), f"Registry mismatch depending on order:\nA: {regA2}\nB: {regB2}"
    # If your plugin is truly fixed, they should both be empty or same shape.
    # If the bug persists, you'll see a test failure indicating a difference.
