"""Polars hopper plugin.

Register a ".hopper" namespace on Polars DataFrame objects for managing
a 'hopper' of filters. The filters are stored as metadata in the `df.config_meta`
namespace (provided by polars-config-meta). They apply themselves when the
necessary columns exist, removing themselves from the hopper once used.
"""

import polars as pl
import polars_config_meta  # ensures df.config_meta is available
from polars.api import register_dataframe_namespace


@register_dataframe_namespace("hopper")
class HopperPlugin:
    """A plugin that stores a list of filter predicates in df.config_meta["hopper_filters"].

    By calling `df.hopper.add_filter(...)`, you add new predicates.
    Calling `df.hopper.apply_ready_filters()` tries each predicate and applies
    it if the DataFrame has all required columns. Successfully applied filters
    are removed from both the old and the new DataFrame (if a new object is created).
    """

    def __init__(self, df: pl.DataFrame):
        """Initialize the HopperPlugin for the given DataFrame.

        Ensures `hopper_filters` is initialized in metadata if not present.
        """
        self._df = df
        meta = df.config_meta.get_metadata()
        if "hopper_filters" not in meta:
            meta["hopper_filters"] = []
            df.config_meta.set(**meta)

    def add_filter(self, predicate) -> None:
        """Add a filter predicate to the hopper.

        The `predicate` must be callable(df: DataFrame) -> boolean Series.
        """
        meta = self._df.config_meta.get_metadata()
        filters = meta.get("hopper_filters", [])
        filters.append(predicate)
        meta["hopper_filters"] = filters
        self._df.config_meta.set(**meta)

    def list_filters(self) -> list:
        """Return the current list of stored filters."""
        return self._df.config_meta.get_metadata().get("hopper_filters", [])

    def apply_ready_filters(self) -> pl.DataFrame:
        """Apply each stored filter if possible; skip filters referencing missing columns.

        Successfully applied filters are removed from self._df's metadata
        and also from the new DataFrame's metadata if a new DataFrame is created.

        Returns the (possibly) newly filtered DataFrame.
        """
        meta_old = self._df.config_meta.get_metadata()
        current_filters = meta_old.get("hopper_filters", [])
        still_pending = []
        filtered_df = self._df

        applied_any = False

        for f in current_filters:
            try:
                # Attempt to filter the DataFrame
                filtered_df = filtered_df.config_meta.filter(f(filtered_df))
            except Exception:
                # Missing column or some other KeyError => remain pending
                still_pending.append(f)
            else:
                # Successfully applied => do not re-add
                applied_any = True

        # If any filter was successfully applied, update old DF's metadata
        meta_old["hopper_filters"] = still_pending
        self._df.config_meta.set(**meta_old)

        # If the filtering created a new DataFrame object, also update the new DF's metadata
        if applied_any and id(filtered_df) != id(self._df):
            meta_new = filtered_df.config_meta.get_metadata()
            meta_new["hopper_filters"] = still_pending
            filtered_df.config_meta.set(**meta_new)

        return filtered_df

    def __getattr__(self, name: str):
        """Fallback for calls like df.hopper.select(...) or df.hopper.with_columns(...).

        If 'name' isn't found on this plugin, try df.config_meta.<name>, else df.<name>.
        """
        df_meta_attr = getattr(self._df.config_meta, name, None)
        if df_meta_attr is not None:
            return df_meta_attr

        df_attr = getattr(self._df, name, None)
        if df_attr is None:
            raise AttributeError(f"Polars DataFrame has no attribute '{name}'")
        return df_attr
