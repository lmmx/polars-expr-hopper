"""Polars hopper plugin.

Register a ".hopper" namespace on Polars DataFrame objects for managing
a 'hopper' of Polars expressions (filters). The filters are stored as
metadata in `df.config_meta` (provided by polars-config-meta). They apply
themselves when the necessary columns exist, removing themselves once used.
"""

import polars as pl
import polars_config_meta  # ensures df.config_meta is available
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
        meta_old = self._df.config_meta.get_metadata()
        current_exprs = meta_old.get("hopper_filters", [])
        still_pending = []
        filtered_df = self._df
        applied_any = False

        for expr in current_exprs:
            try:
                filtered_df = filtered_df.filter(expr)
            except Exception:
                # Missing column or other error => keep the expression for later
                still_pending.append(expr)
            else:
                applied_any = True

        # Update old DF's metadata
        meta_old["hopper_filters"] = still_pending
        self._df.config_meta.set(**meta_old)

        # If we actually created a new DataFrame, also update its metadata
        if applied_any and id(filtered_df) != id(self._df):
            meta_new = filtered_df.config_meta.get_metadata()
            meta_new["hopper_filters"] = still_pending
            filtered_df.config_meta.set(**meta_new)

        return filtered_df

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
