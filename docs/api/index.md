# API Reference

Welcome to the API Reference for **polars-expr-hopper**!

Since **polars-expr-hopper** is a single-module project, all functionality is contained in
`polars_hopper/__init__.py`. In this reference, you’ll find details on the library’s main
plugin class (`HopperPlugin`), which attaches a “hopper” of Polars expressions (`pl.Expr`)
to each `DataFrame` under the `.hopper` namespace. These expressions can be automatically
applied as soon as their required columns appear.

You’ll see method signatures, class methods, and parameters that let you:

- Add expressions (e.g., `df.hopper.add_filter(pl.col("age") > 18)`)
- Check which columns are missing and skip or apply expressions dynamically
- Optionally serialize expressions to JSON/binary for Parquet round-trip (if needed)

If you’re new to the project, you might start with the main [Get Started](../get_started.md) guide
or the README to see basic usage and installation steps. Then come back here for a thorough
look at the plugin’s APIs.

::: polars_hopper
