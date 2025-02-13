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


reg_schema = {
    "idx": pl.Int64,
    "kind": pl.String,  # 'f','s','a'
    "expr": pl.String,  # JSON-serialized expression
    "applied": pl.Boolean,  # whether we've successfully used it
    "root_names": pl.List(pl.String),
}
hopper_reg_key = "hopper_expr_register"
hopper_idx_key = "hopper_max_idx"


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
    # Expression registration
    # -------------------------------------------------------------------------
    def _read_expr_registry(self) -> pl.DataFrame:
        """Parse the NDJSON or JSON registry from self._df.config_meta.

        Return a Polars DataFrame with columns: idx, kind, expr, applied, root_names.
        If none present, return an empty DF with the same schema.
        """
        meta = self._df.config_meta.get_metadata()
        return (
            pl.read_json(meta[hopper_reg_key].encode(), schema=reg_schema)
            if hopper_reg_key in meta
            else pl.DataFrame(schema=reg_schema)
        )

    def _write_expr_registry(self, registry: pl.DataFrame) -> None:
        """Store the given DF in self._df.config_meta as NDJSON/JSON under 'hopper_expr_register'."""
        self._df.config_meta.update({hopper_reg_key: registry.write_json()})

    def _refresh_expr_registry(self) -> None:
        """Refresh the given DF in self._df.config_meta as NDJSON/JSON under 'hopper_expr_register'."""
        self._write_expr_registry(self._read_expr_registry())

    def add_exprs(self, *exprs: pl.Expr, kind: Literal["f", "s", "a"]) -> None:
        """Add one or more Polars expressions to the hopper.

        We maintain a monotonically increasing `hopper_max_idx` and also serialise each
        expression to JSON (using ``expr.meta.serialize(format="json")``) for
        JSON-compatibility in expr registry metadata (stored in the
        `hopper_expr_register` key).


        Parameters
        ----------
        kind : {'f', 's', 'a'}
            Specifies which list in metadata we update:
            - 'f' => hopper_filters
            - 's' => hopper_selects
            - 'a' => hopper_addcols
        exprs : pl.Expr
            The actual Polars expressions to add.

        """
        if not exprs:
            return

        meta = self._df.config_meta.get_metadata()

        # Ensure the correct list in metadata
        hopper_kind_meta_key = {
            "f": "hopper_filters",
            "s": "hopper_selects",
            "a": "hopper_addcols",
        }[kind]

        # Append expressions to the chosen list
        kind_exprs = meta.get(hopper_kind_meta_key, [])
        kind_exprs.extend(exprs)
        meta[hopper_kind_meta_key] = kind_exprs

        # Initialize hopper_max_idx to -1 if not already present
        pre_idx = meta.get(hopper_idx_key, -1)
        pre_reg = self._read_expr_registry()
        # Increment hopper_max_idx for each newly added expression
        post_idx = pre_idx + len(exprs)
        registrands = [
            {
                "idx": expr_offset + pre_idx + 1,
                "kind": kind,
                "expr": expr.meta.serialize(format="json"),
                "applied": False,
                "root_names": expr.meta.root_names(),
            }
            for expr_offset, expr in enumerate(exprs)
        ]
        registry = pl.concat(
            [pre_reg, pl.DataFrame(registrands, schema=reg_schema)],
        )
        self._write_expr_registry(registry)
        meta[hopper_idx_key] = post_idx

        # Write updated metadata back
        self._df.config_meta.update(meta)

    def pop_expr_from_registry(self, expr: pl.Expr) -> bool:
        """Remove earliest row from 'hopper_expr_register' that matches given pl.Expr.

        Do so by comparing JSON-serialised expressions.

        Returns
        -------
        True if a matching row was found and removed; False if no match was found.

        """
        meta = self._df.config_meta.get_metadata()
        hopper_reg_key = "hopper_expr_register"

        if hopper_reg_key not in meta:
            return False  # No registry at all => nothing to remove

        # 1) Convert the JSON string back into a DataFrame
        reg_json = meta[hopper_reg_key].encode()
        registry_df = pl.read_json(reg_json, schema=reg_schema)

        # 2) Serialize the incoming expr
        serialized_expr = expr.meta.serialize(format="json")

        # 3) Find all rows whose 'expr' matches, e.g. ignoring 'applied' or 'kind'
        #    If you want to consider 'kind' or only rows where 'applied'==False,
        #    you can refine this filter accordingly.
        matching = registry_df.filter(pl.col("expr") == serialized_expr).limit(1)

        if matching.is_empty():
            return False  # No match found => do nothing

        # 4) Identify the earliest match by lowest idx
        #    (If you prefer first added or first in insertion order, 'idx' is that.)
        earliest_idx = matching["idx"].min()

        # 5) Remove that row from the registry
        updated_df = registry_df.filter(pl.col("idx") != earliest_idx)

        # 6) Write the updated DF back to NDJSON
        meta[hopper_reg_key] = updated_df.write_json()
        self._df.config_meta.set(**meta)

        return True

    def _apply_expression(
        self,
        df: pl.DataFrame,
        kind: str,
        expr: pl.Expr,
    ) -> pl.DataFrame:
        """Apply the given expression to df depending on 'kind'.

        'f' => df.filter(expr)
        's' => df.select(expr)
        'a' => df.with_columns(expr)
        """
        if kind == "f":
            return df.filter(expr)
        elif kind == "s":
            return df.select(expr)
        elif kind == "a":
            return df.with_columns(expr)
        else:
            raise ValueError(f"Unknown expression kind '{kind}'")

    def apply_ready_exprs(self, *kinds: Literal["f", "s", "a"]) -> pl.DataFrame:
        """Apply any expressions of all kind(s), if the needed columns exist.

          - Filters: we pop from the registry if the expression is successfully applied.
          - Selects/Addcols: we do NOT remove from the registry (tests expect that logic).

        Each expression is tried in turn:
          - kind == 'f' => df.filter(expr)
          - kind == 's' => df.select(expr)
          - kind == 'a' => df.with_columns(expr)

        If needed columns are missing, that expression remains pending. If we successfully
        apply a filter expression (kind='f'), we call pop_expr_from_registry(expr).
        The original code never used the registry for selects/addcols, so we skip it there.

        Returns
        -------
        A new (possibly transformed) DataFrame. If it differs from self._df,
        polars-config-meta merges metadata automatically.

        """
        return self.apply_ready_exprs_kinds("f", "s", "a")

    def apply_ready_exprs_kinds(self, *kinds: Literal["f", "s", "a"]) -> pl.DataFrame:
        """Apply any expressions of the specified kind(s), if the needed columns exist.

          - Filters: we pop from the registry if the expression is successfully applied.
          - Selects/Addcols: we do NOT remove from the registry (tests expect that logic).

        Each expression is tried in turn:
          - kind == 'f' => df.filter(expr)
          - kind == 's' => df.select(expr)
          - kind == 'a' => df.with_columns(expr)

        If needed columns are missing, that expression remains pending. If we successfully
        apply a filter expression (kind='f'), we call pop_expr_from_registry(expr).
        The original code never used the registry for selects/addcols, so we skip it there.

        Returns
        -------
        A new (possibly transformed) DataFrame. If it differs from self._df,
        polars-config-meta merges metadata automatically.

        """
        if not kinds:
            raise ValueError(
                "No expression kinds specified. Provide at least one of 'f','s','a'.",
            )

        registry = self._read_expr_registry()
        if registry.is_empty():
            return self._df

        # We'll apply them in the order the user specified
        new_df = self._df
        for kind in kinds:
            # Which metadata key do we read/write (hopper_filters, hopper_selects, or hopper_addcols)?
            meta_key = {
                "f": "hopper_filters",
                "s": "hopper_selects",
                "a": "hopper_addcols",
            }[kind]

            meta_pre = self._df.config_meta.get_metadata()
            current_exprs = meta_pre.get(meta_key, [])

            still_pending = []
            changed_any = False

            # We'll track available columns after each expression is applied
            avail_cols = set(new_df.collect_schema())

            for expr in current_exprs:
                needed_cols = set(expr.meta.root_names())
                if needed_cols <= avail_cols:
                    # Optionally pop from registry ONLY if 'kind' == 'f' (filters).
                    # Your existing tests expect that selects/addcols do not remove from the registry.
                    r0 = self._read_expr_registry()
                    removed = self.pop_expr_from_registry(expr)
                    r1 = self._read_expr_registry()
                    assert (
                        n_popped := len(r0) - len(r1)
                    ) == 1, f"Registry popped {n_popped} items"
                    if not removed:
                        raise ValueError(f"Inconsistent registry: {expr} not found")

                    # Actually apply the expression
                    new_df = self._apply_expression(new_df, kind, expr)
                    changed_any = True
                    # Update available columns in case columns changed
                    avail_cols = set(new_df.collect_schema())
                else:
                    # Missing columns => keep it pending
                    still_pending.append(expr)

            # Update old DF's metadata list (filters/selects/addcols)
            meta_pre[meta_key] = still_pending
            self._df.config_meta.update(meta_pre)

            # If new_df is indeed a new object, also update that DF's metadata
            if changed_any and id(new_df) != id(self._df):
                self._refresh_expr_registry()
                meta_post = new_df.config_meta.get_metadata()
                meta_post[meta_key] = still_pending
                fresh_registry = self._df.config_meta.get_metadata()[hopper_reg_key]
                meta_post[hopper_reg_key] = fresh_registry
                new_df.config_meta.update(meta_post)

        return new_df

    # -------------------------------------------------------------------------
    # Filter storage and application
    # -------------------------------------------------------------------------
    def add_filters(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars filter expressions to the hopper.

        Each expression is typically used in `df.filter(expr)`, returning
        a boolean mask. They remain in the queue until the columns they need
        are present, at which point they are applied (and removed).
        """
        self.add_exprs(*exprs, kind="f")

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
        return self.apply_ready_exprs_kinds("f")

    # -------------------------------------------------------------------------
    # Select storage and application
    # -------------------------------------------------------------------------
    def add_selects(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars select expressions to the hopper.

        These expressions are used in `df.select(expr)`. Each expression
        typically yields a column transformation, or just a column reference
        (like `pl.col("foo").alias("bar")`).
        """
        self.add_exprs(*exprs, kind="s")

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
        return self.apply_ready_exprs_kinds("s")

    # -------------------------------------------------------------------------
    # With columns storage and application
    # -------------------------------------------------------------------------
    def add_addcols(self, *exprs: pl.Expr) -> None:
        """Add one or more Polars with_columns expressions to the hopper.

        These expressions are used in `df.with_columns(expr)`. Each expression
        typically yields a column addition or overwrite, or just a column reference
        (like `pl.col("foo").alias("bar")`).
        """
        self.add_exprs(*exprs, kind="a")

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
        return self.apply_ready_exprs_kinds("a")

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
