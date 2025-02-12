# polars-expr-hopper

<!-- [![downloads](https://static.pepy.tech/badge/polars-expr-hopper/month)](https://pepy.tech/project/polars-expr-hopper) -->
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
[![PyPI](https://img.shields.io/pypi/v/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![License](https://img.shields.io/pypi/l/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/lmmx/polars-expr-hopper/master.svg)](https://results.pre-commit.ci/latest/github/lmmx/polars-expr-hopper/master)

**Polars plugin providing a ‘expression hopper’**—a flexible, DataFrame-level container of expressions (predicates such as filter) that apply themselves **as soon as** the relevant columns are available.

Powered by [polars-config-meta](https://pypi.org/project/polars-config-meta/) for persistent DataFrame-level metadata.

Simplify data pipelines by storing your expressions in a single location and letting them apply **as soon as** the corresponding columns exist in the DataFrame schema.

## Installation

```bash
pip install polars-expr-hopper
```

> The `polars` dependency is required but not included in the package by default.
> It is shipped as an optional extra which can be activated by passing it in square brackets:
> ```bash
> pip install polars-expr-hopper[polars]           # for standard Polars
> pip install polars-expr-hopper[polars-lts-cpu]   # for older CPUs
> ```

### Requirements

- Python 3.9+
- Polars (any recent version, installed via `[polars]` or `[polars-lts-cpu]` extras)
- _(Optional)_ [pyarrow](https://pypi.org/project/pyarrow) if you want Parquet I/O features that preserve the hopper metadata

## Features

- **DataFrame-Level Filter Management**: Store multiple predicate functions on a DataFrame via the `.hopper` namespace.
- **Apply When Ready**: Each expression is automatically applied once the DataFrame has all columns required by that expression.
- **Namespace Plugin**: Access everything through `df.hopper.*(...)`—no subclassing or monkey-patching.
- **Metadata Preservation**: Transformations called through `df.hopper.<method>()` keep the same expression hopper on the new DataFrame.
- **No Central Orchestration**: Avoid fiddly pipeline step names or schemas—just attach your expressions once, and they get applied in the right order automatically.

## Usage

### Basic Usage Example

```python
import polars as pl
import polars_hopper  # This registers the .hopper plugin under pl.DataFrame

# Create an initial DataFrame
df = pl.DataFrame({
    "user_id": [1, 2, 3, 0],
    "name": ["Alice", "Bob", "Charlie", "NullUser"]
})

# Add expressions to the hopper:
#  - This one needs 'user_id' (which exists now).
#  - We'll also add one needing a future 'age' column.
df.hopper.add_filter(pl.col("user_id") != 0)
df.hopper.add_filter(pl.col("age") > 18)  # 'age' doesn't exist yet

# Apply what we can; the first filter is immediately valid:
df = df.hopper.apply_ready_filters()
print(df)
# Rows with user_id=0 are dropped.

# Now let's do a transformation that adds an 'age' column.
# By calling df.hopper.with_columns(...), the plugin
# automatically copies the hopper metadata to the new DataFrame.
df2 = df.hopper.with_columns(
    pl.Series("age", [25, 15, 30])  # new column
)

# Now the second filter can be applied:
df2 = df2.hopper.apply_ready_filters()
print(df2)
# Only rows with age > 18 remain. That filter expression is then removed from the hopper.
```

### How It Works

Internally, **polars-expr-hopper** attaches a small “manager” object to your `DataFrame` (similar to how [polars-config-meta](https://pypi.org/project/polars-config-meta/) does). This manager:

- Keeps track of a list (or set) of expressions (callable predicates).
- On `apply_ready_filters()`, checks each filter expression’s required columns.
- Applies those filter expressions that are valid for the current schema.
- Removes applied filter expressions from the “hopper.”
- Copies the hopper forward when you call `df.hopper.select(...)`, `df.hopper.with_columns(...)`, etc.

Because we use Polars’ plugin system and store the metadata in a dictionary keyed by `id(df)`, the same patterns (weak references, no monkey-patching, etc.) described in **polars-config-meta** apply here as well.

### API Methods

- **`add_filter(predicate: Callable[[pl.DataFrame], pl.Series])`**
  Add a new predicate (lambda, function, Polars expression, etc.) to the hopper.

- **`apply_ready_filters() -> pl.DataFrame`**
  Check all stored predicates for which columns they need. Apply every predicate that is *now* valid, returning a filtered DataFrame. Already-applied filters are removed from the hopper.

- **`list_filters() -> List[Callable]`**
  Return the still-pending filters in the hopper. Useful for debugging or inspection.

- **Any existing Polars method** (like `with_columns`, `select`, `filter`, `groupby`, etc.) can be accessed via `df.hopper.with_columns(...)` or `df.hopper.filter(...)`. This ensures the new DataFrame is automatically registered with the plugin and the hopper data is copied forward.

## Contributing

Maintained by [Louis Maddox](https://github.com/lmmx/polars-expr-hopper). Contributions welcome!

1. **Issues & Discussions**: Please open a GitHub issue or discussion for bugs, feature requests, or questions.
2. **Pull Requests**: PRs are welcome!
   - Install the dev extra (e.g. with [uv](https://docs.astral.sh/uv/)):
     `uv pip install -e .[dev]`
   - Run tests (when available) and include updates to docs or examples if relevant.
   - If reporting a bug, please include the version and any error messages/tracebacks.

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).
