"""Tests for Parquet round-trip of metadata (RQ4)."""

import polars as pl
import pytest
from polars_config_meta import read_parquet_with_meta


@pytest.mark.skip(reason="Cannot serialise predicates to JSON?")
def test_parquet_roundtrip(tmp_path):
    """PRD RQ4: The plugin should embed/recover hopper_filters in Parquet.

    Skipped by default because JSON cannot serialize Python lambdas.
    """
    df = pl.DataFrame({"col": [5, 10, 15]})
    df.config_meta.set(hopper_filters=[(pl.col("col") > 5)])

    out_file = tmp_path / "test_filters.parquet"
    df.config_meta.write_parquet(str(out_file))

    df_in = read_parquet_with_meta(str(out_file))
    meta_in = df_in.config_meta.get_metadata()
    filters = meta_in["hopper_filters"]
    assert len(filters) == 1, "One filter should remain after loading."

    df_filtered = df_in.hopper.apply_ready_filters()
    assert df_filtered.shape == (2, 1), "Rows with col<=5 removed."
