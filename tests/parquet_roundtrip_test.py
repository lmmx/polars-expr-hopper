"""Verify correct writing to Parquet as JSON file-level metadata and reading back."""

import io

import polars as pl
import pytest
from polars_config_meta import read_parquet_with_meta


HAS_PYARROW = False
try:
    import pyarrow  # noqa: F401

    HAS_PYARROW = True
except ImportError:
    pass


@pytest.mark.skipif(
    not HAS_PYARROW,
    reason="pyarrow not installed for Parquet round-trip",
)
def test_parquet_roundtrip_json(tmp_path):
    """Demonstrate writing a DF with pl.Expr filters to Parquet and back.

    Auto-converting exprs to JSON strings in 'hopper_filters_serialised'.
    """
    df = pl.DataFrame({"col": [5, 10, 15]})
    df.hopper.add_filters(pl.col("col") > 5)

    out_file = tmp_path / "test_filters.parquet"
    # This triggers the custom _write_parquet_plugin code
    df.hopper.write_parquet(str(out_file), format="json")

    # Now read it back
    df_in = read_parquet_with_meta(str(out_file))
    meta_in = df_in.config_meta.get_metadata()

    # The plugin won't auto-restore expressions at read time, so let's see what we have
    # We'll see 'hopper_filters' is empty, but 'hopper_filters_serialised' is present
    print("Metadata after reading:", meta_in.keys())
    # -> 'hopper_filters_serialised' is a tuple (list-of-JSON-strings, "json") or maybe just leftover
    # The easiest approach: manually re-initialise the plugin / restore expressions

    # Manually re-hydrate the expressions
    # If we want to replicate the logic from the plugin's restore step:
    if "hopper_filters_serialised" in meta_in:
        ser_data, ser_fmt = meta_in["hopper_filters_serialised"]
        restored_exprs = []
        for item in ser_data:
            expr = pl.Expr.deserialize(io.StringIO(item), format=ser_fmt)
            restored_exprs.append(expr)

        meta_in["hopper_filters"] = restored_exprs
        del meta_in["hopper_filters_serialised"]
        df_in.config_meta.set(**meta_in)

    # Now apply filters
    df_filtered = df_in.hopper.apply_ready_filters()
    assert df_filtered.shape == (2, 1), "Should remove rows with col <= 5"
