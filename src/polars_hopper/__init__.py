"""Polars hopper plugin.

Register a ".hopper" namespace on Polars DataFrame objects for managing
a 'hopper' of Polars expressions (e.g. filters). The expressions are stored as
metadata in `df.config_meta` (provided by polars-config-meta). They apply
themselves when the necessary columns exist, removing themselves once used.
"""

import io
from typing import Literal, Union

import polars as pl
import polars_config_meta  # noqa: F401
from polars.api import register_dataframe_namespace


@register_dataframe_namespace("hopper")
class HopperPlugin:
    """Hopper plugin for storing and applying Polars filter expressions.

    By calling `df.hopper.add_filters(*expr)`, you add Polars expressions
    (pl.Expr). Each expression is applied as `df.filter(expr)` if the
    required columns exist. Successfully applied filters are removed
    from both the old and new DataFrame objects.
    """

    def __init__(self, df: pl.DataFrame):
        """Ensure a 'hopper_filters' key in metadata if not present."""
        self._df = df
        meta = df.config_meta.get_metadata()
        if "hopper_filters" not in meta:
            meta["hopper_filters"] = []
            df.config_meta.set(**meta)

    def add_filters(self, *exprs: pl.Expr) -> None:
        """Add a Polars expression to the hopper.

        This expression should evaluate to a boolean mask when used in `df.filter(expr)`.
        """
        meta = self._df.config_meta.get_metadata()
        filters = meta.get("hopper_filters", [])
        filters.extend(exprs)
        meta["hopper_filters"] = filters
        self._df.config_meta.set(**meta)

    def list_filters(self) -> list[pl.Expr]:
        """Return the list of pending Polars expressions."""
        return self._df.config_meta.get_metadata().get("hopper_filters", [])

    def apply_ready_filters(self) -> pl.DataFrame:
        """Apply any stored expressions if the referenced columns exist.

        Each expression is tried in turn with `df.filter(expr)`. If a KeyError
        or similar occurs (missing columns), the expression remains pending.

        Returns
        -------
        A new (possibly filtered) DataFrame. If it differs from self._df,
        polars-config-meta merges metadata automatically.

        """
        meta_pre = self._df.config_meta.get_metadata()
        current_exprs = meta_pre.get("hopper_filters", [])
        still_pending = []
        filtered_df = self._df
        applied_any = False

        avail_cols = set(filtered_df.columns)

        for expr in current_exprs:
            needed_cols = set(expr.meta.root_names())
            if needed_cols <= avail_cols:
                filtered_df = filtered_df.filter(expr)
                applied_any = True
            else:
                # Missing column => keep the expression for later
                still_pending.append(expr)

        # Update old DF's metadata
        meta_pre["hopper_filters"] = still_pending
        self._df.config_meta.set(**meta_pre)

        # If we actually created a new DataFrame, also update its metadata
        if applied_any and id(filtered_df) != id(self._df):
            meta_post = filtered_df.config_meta.get_metadata()
            meta_post["hopper_filters"] = still_pending
            filtered_df.config_meta.set(**meta_post)

        return filtered_df

    # ------------------------------------------------------------
    # Optional: "Auto-serialisation" on write_parquet
    # ------------------------------------------------------------

    def _write_parquet_plugin(
        self,
        file: str,
        *,
        format: Literal["binary", "json"] = "json",
        **kwargs,
    ) -> None:
        """Intercept df.config_meta.write_parquet(...).

        Steps:
          1. Convert in-memory pl.Expr to a safe storable format (json/binary).
          2. Remove the original pl.Expr objects from 'hopper_filters'.
          3. Call the real config_meta write_parquet.
          4. Restore the original in-memory expressions after writing.

        By default, we use "json" for easier storage in metadata,
        but "binary" is also valid if you handle it carefully.
        """
        meta = self._df.config_meta.get_metadata()
        exprs = meta.get("hopper_filters", [])

        # 1) Convert each expression to the chosen format
        serialised_data = []
        for expr in exprs:
            data = expr.meta.serialize(format=format)
            serialised_data.append(data)

        # 2) Store them in a side key, remove original expr objects
        meta["hopper_filters_serialised"] = (serialised_data, format)
        meta["hopper_filters"] = []
        self._df.config_meta.set(**meta)

        # 3) Actually write parquet using polars_config_meta's fallback
        original_write_parquet = getattr(self._df.config_meta, "write_parquet", None)
        if original_write_parquet is None:
            raise AttributeError("No write_parquet found in df.config_meta.")
        original_write_parquet(file, **kwargs)

        # 4) Restore the original in-memory expressions
        #    so the user session stays consistent
        #    We'll do the reverse of what we'd do after reading
        restored_exprs = []
        ser_data, ser_fmt = self._df.config_meta.get_metadata()[
            "hopper_filters_serialised"
        ]
        for item in ser_data:
            if ser_fmt == "json":
                expr = pl.Expr.deserialize(io.StringIO(item), format="json")
            else:  # "binary"
                expr = pl.Expr.deserialize(io.BytesIO(item), format="binary")
            restored_exprs.append(expr)

        meta_restored = self._df.config_meta.get_metadata()
        meta_restored["hopper_filters"] = restored_exprs
        del meta_restored["hopper_filters_serialised"]
        self._df.config_meta.set(**meta_restored)

    def __getattr__(self, name: str):
        """Fallback for calls like df.hopper.select(...).

        Intercept 'write_parquet' calls for auto-serialisation.
        """
        if name == "write_parquet":
            return self._write_parquet_plugin

        df_meta_attr = getattr(self._df.config_meta, name, None)
        if df_meta_attr is not None:
            return df_meta_attr

        df_attr = getattr(self._df, name, None)
        if df_attr is None:
            raise AttributeError(f"Polars DataFrame has no attribute '{name}'")
        return df_attr
