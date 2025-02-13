"""Polars hopper plugin with both filter and select 'queues'.

Register a ".hopper" namespace on Polars DataFrame objects for managing
a 'hopper' of Polars expressions (e.g. filters, selects). The expressions are
stored as metadata in `df.config_meta`. They apply themselves when the
necessary columns exist, removing themselves once used.
"""

import io
from typing import Literal, Union

import polars as pl
import polars_config_meta  # noqa: F401
from polars.api import register_dataframe_namespace


@register_dataframe_namespace("hopper")
class HopperPlugin:
    """Hopper plugin for storing and applying Polars filter/select expressions.

    By calling `df.hopper.add_filters(*exprs)`, you add Polars expressions
    that should evaluate to a boolean mask (for filtering).
    By calling `df.hopper.add_selects(*exprs)`, you add Polars expressions
    that transform or select columns when calling `df.select(expr)`.
    """

    def __init__(self, df: pl.DataFrame):
        """Ensure required metadata keys exist if not present."""
        self._df = df
        meta = df.config_meta.get_metadata()

        if "hopper_filters" not in meta:
            meta["hopper_filters"] = []
        if "hopper_selects" not in meta:
            meta["hopper_selects"] = []
        if "hopper_addcols" not in meta:
            meta["hopper_addcols"] = []

        df.config_meta.update(meta)

    # -------------------------------------------------------------------------
    # Filter storage and application
    # -------------------------------------------------------------------------
    def add_filters(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars filter expressions to the hopper.

        Each expression is typically used in `df.filter(expr)`, returning
        a boolean mask. They remain in the queue until the columns they need
        are present, at which point they are applied (and removed).
        """
        meta = self._df.config_meta.get_metadata()
        filters = meta.get("hopper_filters", [])
        filters.extend(exprs)
        meta["hopper_filters"] = filters
        self._df.config_meta.update(meta)

    def list_filters(self) -> list[pl.Expr]:
        """Return the list of pending Polars filter expressions."""
        return self._df.config_meta.get_metadata().get("hopper_filters", [])

    def apply_ready_filters(self) -> pl.DataFrame:
        """Apply any stored filter expressions if referenced columns exist.

        Each expression is tried in turn with `df.filter(expr)`. If missing
        columns, that expression remains pending for later.

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

        avail_cols = set(filtered_df.collect_schema())

        for expr in current_exprs:
            needed_cols = set(expr.meta.root_names())
            if needed_cols <= avail_cols:
                # All needed columns exist; apply the filter
                filtered_df = filtered_df.hopper.filter(expr)
                applied_any = True
                # Update available columns if needed
                avail_cols = set(filtered_df.collect_schema())
            else:
                # Missing column => keep the expression for later
                still_pending.append(expr)

        # Update old DF's metadata
        meta_pre["hopper_filters"] = still_pending
        self._df.config_meta.update(meta_pre)

        # If we actually created a new DataFrame, also update its metadata
        if applied_any and id(filtered_df) != id(self._df):
            meta_post = filtered_df.config_meta.get_metadata()
            meta_post["hopper_filters"] = still_pending
            filtered_df.config_meta.update(meta_post)

        return filtered_df

    # -------------------------------------------------------------------------
    # Select storage and application
    # -------------------------------------------------------------------------
    def add_selects(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars select expressions to the hopper.

        These expressions are used in `df.select(expr)`. Each expression
        typically yields a column transformation, or just a column reference
        (like `pl.col("foo").alias("bar")`).
        """
        meta = self._df.config_meta.get_metadata()
        selects = meta.get("hopper_selects", [])
        selects.extend(exprs)
        meta["hopper_selects"] = selects
        self._df.config_meta.update(meta)

    def list_selects(self) -> list[pl.Expr]:
        """Return the list of pending Polars select expressions."""
        return self._df.config_meta.get_metadata().get("hopper_selects", [])

    def apply_ready_selects(self) -> pl.DataFrame:
        """Apply any stored select expressions if columns exist.

        We attempt each select expression in turn. Because `df.select(expr)`
        replaces the DataFrame columns entirely, you should be aware that
        subsequent select expressions apply to the new shape of the DataFrame.

        If any required columns are missing, that expression remains pending.

        Returns
        -------
        A new DataFrame with the successfully selected/transformed columns.

        """
        meta_pre = self._df.config_meta.get_metadata()
        current_exprs = meta_pre.get("hopper_selects", [])
        still_pending = []
        selected_df = self._df
        applied_any = False

        for expr in current_exprs:
            needed_cols = set(expr.meta.root_names())
            avail_cols = set(selected_df.collect_schema())
            if needed_cols <= avail_cols:
                # We can apply this select
                selected_df = selected_df.hopper.select(expr)
                applied_any = True
            else:
                # Missing columns => keep in the queue
                still_pending.append(expr)

        # Update old DF's metadata
        meta_pre["hopper_selects"] = still_pending
        self._df.config_meta.update(meta_pre)

        # If a new DataFrame was produced, update its metadata as well
        if applied_any and id(selected_df) != id(self._df):
            meta_post = selected_df.config_meta.get_metadata()
            meta_post["hopper_selects"] = still_pending
            selected_df.config_meta.update(meta_post)

        return selected_df

    # -------------------------------------------------------------------------
    # With columns storage and application
    # -------------------------------------------------------------------------
    def add_addcols(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars with_columns expressions to the hopper.

        These expressions are used in `df.with_columns(expr)`. Each expression
        typically yields a column addition or overwrite, or just a column reference
        (like `pl.col("foo").alias("bar")`).
        """
        meta = self._df.config_meta.get_metadata()
        addcols = meta.get("hopper_addcols", [])
        addcols.extend(exprs)
        meta["hopper_addcols"] = addcols
        self._df.config_meta.update(meta)

    def list_addcols(self) -> list[pl.Expr]:
        """Return the list of pending Polars with_columns expressions."""
        return self._df.config_meta.get_metadata().get("hopper_addcols", [])

    def apply_ready_addcols(self) -> pl.DataFrame:
        """Apply any stored with_columns expressions if columns exist.

        We attempt each with_columns expression in turn. Because `df.with_columns(expr)`
        adds the DataFrame columns, you should be aware that subsequent select expressions
        apply to the new shape of the DataFrame.

        If any required columns are missing, that expression remains pending.

        Returns
        -------
        A new DataFrame with the successfully added/overwritten columns.

        """
        meta_pre = self._df.config_meta.get_metadata()
        current_exprs = meta_pre.get("hopper_addcols", [])
        still_pending = []
        added_df = self._df
        applied_any = False

        for expr in current_exprs:
            needed_cols = set(expr.meta.root_names())
            avail_cols = set(added_df.collect_schema())
            if needed_cols <= avail_cols:
                # We can apply this with_columns
                added_df = added_df.hopper.with_columns(expr)
                applied_any = True
            else:
                # Missing columns => keep in the queue
                still_pending.append(expr)

        # Update old DF's metadata
        meta_pre["hopper_addcols"] = still_pending
        self._df.config_meta.update(meta_pre)

        # If a new DataFrame was produced, update its metadata as well
        if applied_any and id(added_df) != id(self._df):
            meta_post = added_df.config_meta.get_metadata()
            meta_post["hopper_addcols"] = still_pending
            added_df.config_meta.update(meta_post)

        return added_df

    # -------------------------------------------------------------------------
    # Serialization override when writing parquet
    # -------------------------------------------------------------------------
    def _write_parquet_plugin(
        self,
        file: str,
        *,
        format: Literal["binary", "json"] = "json",
        **kwargs,
    ) -> None:
        """Intercept df.config_meta.write_parquet(...).

        Steps:
          1. Convert in-memory pl.Expr (both filters and selects)
             to a safe storable format (json/binary).
          2. Remove the original pl.Expr objects from their queues.
          3. Call the real config_meta write_parquet.
          4. Restore the original in-memory expressions after writing.
        """
        meta = self._df.config_meta.get_metadata()

        # 1) Convert each filter expression
        exprs_filters = meta.get("hopper_filters", [])
        serialized_filters = [
            expr.meta.serialize(format=format) for expr in exprs_filters
        ]

        # 1b) Convert each select expression
        exprs_selects = meta.get("hopper_selects", [])
        serialized_selects = [
            expr.meta.serialize(format=format) for expr in exprs_selects
        ]

        # 2) Store them in side keys, remove original expression objects
        meta["hopper_filters_serialised"] = (serialized_filters, format)
        meta["hopper_filters"] = []
        meta["hopper_selects_serialised"] = (serialized_selects, format)
        meta["hopper_selects"] = []
        self._df.config_meta.update(meta)

        # 3) Actually write parquet using polars_config_meta's fallback
        original_write_parquet = getattr(self._df.config_meta, "write_parquet", None)
        if original_write_parquet is None:
            raise AttributeError("No write_parquet found in df.config_meta.")
        original_write_parquet(file, **kwargs)

        # 4) Restore the original in-memory expressions
        meta_after = self._df.config_meta.get_metadata()
        f_ser_data, f_ser_fmt = meta_after["hopper_filters_serialised"]
        s_ser_data, s_ser_fmt = meta_after["hopper_selects_serialised"]

        restored_filters = []
        for item in f_ser_data:
            if f_ser_fmt == "json":
                restored_filters.append(
                    pl.Expr.deserialize(io.StringIO(item), format="json"),
                )
            else:  # "binary"
                restored_filters.append(
                    pl.Expr.deserialize(io.BytesIO(item), format="binary"),
                )

        restored_selects = []
        for item in s_ser_data:
            if s_ser_fmt == "json":
                restored_selects.append(
                    pl.Expr.deserialize(io.StringIO(item), format="json"),
                )
            else:  # "binary"
                restored_selects.append(
                    pl.Expr.deserialize(io.BytesIO(item), format="binary"),
                )

        meta_after["hopper_filters"] = restored_filters
        meta_after["hopper_selects"] = restored_selects

        # Cleanup
        del meta_after["hopper_filters_serialised"]
        del meta_after["hopper_selects_serialised"]

        self._df.config_meta.update(meta_after)

    def __getattr__(self, name: str):
        """Fallback for calls like df.hopper.select(...), etc.

        Intercept 'write_parquet' calls for auto-serialisation.
        Otherwise, just pass through to df.config_meta or df itself.
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
