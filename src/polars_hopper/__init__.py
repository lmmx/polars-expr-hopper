"""Polars hopper plugin.

Register a ".hopper" namespace on Polars DataFrame objects for managing
a 'hopper' of Polars expressions (filters). The filters are stored as
metadata in `df.config_meta` (provided by polars-config-meta). They apply
themselves when the necessary columns exist, removing themselves once used.
"""

from typing import Literal

import polars as pl
import polars_config_meta
from polars.api import register_dataframe_namespace


@register_dataframe_namespace("hopper")
class HopperPlugin:
    """Hopper plugin for storing and applying Polars filter expressions.

    By calling `df.hopper.add_filter(expr)`, you add Polars expressions
    (pl.Expr). Each expression is applied as `df.filter(expr)` if the
    required columns exist. Successfully applied filters are removed
    from both the old and new DataFrame objects.
    """

    def __init__(self, df: pl.DataFrame):
        """Initialize the plugin for the given DataFrame, ensuring hopper_filters in metadata."""
        self._df = df
        meta = df.config_meta.get_metadata()
        if "hopper_filters" not in meta:
            meta["hopper_filters"] = []
            df.config_meta.set(**meta)

    def add_filter(self, expr: pl.Expr) -> None:
        """Add a Polars expression to the hopper.

        This expression should evaluate to a boolean mask when used in `df.filter(expr)`.
        """
        meta = self._df.config_meta.get_metadata()
        filters = meta.get("hopper_filters", [])
        filters.append(expr)
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

        for expr in current_exprs:
            needed_cols = expr.meta.root_names()
            available_cols = filtered_df.collect_schema()
            if all(c in available_cols for c in needed_cols):
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

    def serialize_filters(
        self,
        format: Literal["binary", "json"] = "binary",
    ) -> list[str | bytes]:
        """
        Convert each stored pl.Expr into either binary (bytes) or JSON (str).

        Parameters
        ----------
        format
            "binary" (default) => returns a list of bytes
            "json" => returns a list of strings

        Returns
        -------
        A list of serialized data (bytes or strings) that can be stored externally.
        """
        exprs = self.list_filters()
        serialized_list = []
        for expr in exprs:
            data = expr.meta.serialize(format=format)
            # If 'binary' => data is bytes, if 'json' => data is a string
            serialized_list.append(data)
        return serialized_list

    def deserialize_filters(
        self,
        serialized_list: list[str | bytes],
        format: Literal["binary", "json"] = "binary",
    ) -> None:
        """
        Replace existing filters with newly deserialized expressions.

        Parameters
        ----------
        serialized_list
            A list of data as returned by serialize_filters().
        format
            "binary" or "json" (default "binary") to match how they were serialized.
        """
        new_exprs = []
        for item in serialized_list:
            if format == "json":
                # item is a string
                expr = pl.Expr.deserialize(io.StringIO(item), format="json")
            else:
                # item is bytes
                expr = pl.Expr.deserialize(io.BytesIO(item), format="binary")
            new_exprs.append(expr)

        meta = self._df.config_meta.get_metadata()
        meta["hopper_filters"] = new_exprs
        self._df.config_meta.set(**meta)

    def __getattr__(self, name: str):
        """Fallback for calls like df.hopper.select(...).

        If 'name' is not a method in this plugin, we try df.config_meta.<name>,
        then fallback to df.<name>.
        """
        df_meta_attr = getattr(self._df.config_meta, name, None)
        if df_meta_attr is not None:
            return df_meta_attr

        df_attr = getattr(self._df, name, None)
        if df_attr is None:
            raise AttributeError(f"Polars DataFrame has no attribute '{name}'")
        return df_attr
