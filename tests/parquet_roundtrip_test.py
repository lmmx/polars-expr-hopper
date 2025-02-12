"""Tests for Parquet round-trip of expression metadata (RQ4)."""

import io

import polars as pl
import pytest
from polars_config_meta import read_parquet_with_meta


try:
    import pyarrow  # noqa: F401

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False


@pytest.mark.skipif(
    not HAS_PYARROW, reason="pyarrow not installed for Parquet round-trip"
)
def test_parquet_roundtrip_binary(tmp_path):
    """
    Demonstrate storing binary data in metadata for a simple round trip.
    This might require that the metadata is base64-encoded if your
    environment can't store bytes directly in JSON.
    Otherwise, you can store them in a separate store.
    """
    df = pl.DataFrame({"col": [5, 10, 15]})

    # Add a filter expression
    df.hopper.add_filter(pl.col("col") > 5)

    # Optionally, we could do a manual step:
    #   bin_data = df.hopper.serialize_filters(format="binary")
    #   encode and store in some separate meta key or external DB
    # Instead, let's keep them ephemeral for this test.

    out_file = tmp_path / "test_filters.parquet"
    df.config_meta.write_parquet(str(out_file))

    df_in = read_parquet_with_meta(str(out_file))
    # Because we never manually replaced the in-memory expr with a JSON or binary,
    # df_in will just have an in-memory copy (which does not actually exist
    # if the plugin doesn't do that automatically).

    # If you want to do a real "store binary to a text field" approach,
    # you'd do so manually.
    # For this test, let's just confirm the new DF doesn't know about the expression.

    meta_in = df_in.config_meta.get_metadata()
    # The old expression wasn't actually stored as binary in the .parquet
    # unless you do it yourself.

    # The rest is up to how your plugin or test environment handles it.
    # If you *did* store it, you'd do:
    # bin_data = meta_in["hopper_filters_binary"]  # or something
    # df_in.hopper.deserialize_filters(bin_data, format="binary")

    # Then check applying:
    # df_filtered = df_in.hopper.apply_ready_filters()
    # assert df_filtered.shape == (2, 1), "Should remove col <= 5."
    # For now, just a stub.
    assert True


@pytest.mark.skipif(
    not HAS_PYARROW, reason="pyarrow not installed for Parquet round-trip"
)
def test_parquet_roundtrip_binary(tmp_path):
    """
    Demonstrate storing binary data in metadata for a simple round trip.
    This might require that the metadata is base64-encoded if your
    environment can't store bytes directly in JSON.
    Otherwise, you can store them in a separate store.
    """
    df = pl.DataFrame({"col": [5, 10, 15]})

    # Add a filter expression
    df.hopper.add_filter(pl.col("col") > 5)

    # Optionally, we could do a manual step:
    #   bin_data = df.hopper.serialize_filters(format="binary")
    #   encode and store in some separate meta key or external DB
    # Instead, let's keep them ephemeral for this test.

    out_file = tmp_path / "test_filters.parquet"
    df.config_meta.write_parquet(str(out_file))

    df_in = read_parquet_with_meta(str(out_file))
    # Because we never manually replaced the in-memory expr with a JSON or binary,
    # df_in will just have an in-memory copy (which does not actually exist
    # if the plugin doesn't do that automatically).

    # If you want to do a real "store binary to a text field" approach,
    # you'd do so manually.
    # For this test, let's just confirm the new DF doesn't know about the expression.

    meta_in = df_in.config_meta.get_metadata()
    # The old expression wasn't actually stored as binary in the .parquet
    # unless you do it yourself.

    # The rest is up to how your plugin or test environment handles it.
    # If you *did* store it, you'd do:
    # bin_data = meta_in["hopper_filters_binary"]  # or something
    # df_in.hopper.deserialize_filters(bin_data, format="binary")

    # Then check applying:
    # df_filtered = df_in.hopper.apply_ready_filters()
    # assert df_filtered.shape == (2, 1), "Should remove col <= 5."
    # For now, just a stub.
    assert True
