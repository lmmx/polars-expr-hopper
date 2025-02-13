# polars-expr-hopper

<!-- [![downloads](https://static.pepy.tech/badge/polars-expr-hopper/month)](https://pepy.tech/project/polars-expr-hopper) -->
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
[![PyPI](https://img.shields.io/pypi/v/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![License](https://img.shields.io/pypi/l/polars-expr-hopper.svg)](https://pypi.org/project/polars-expr-hopper)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/lmmx/polars-expr-hopper/master.svg)](https://results.pre-commit.ci/latest/github/lmmx/polars-expr-hopper/master)

**Polars plugin providing an “expression hopper”**—a flexible, DataFrame-level container of **Polars expressions** (`pl.Expr`) that apply themselves **as soon as** the relevant columns are available.

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
- _(Optional)_ [pyarrow](https://pypi.org/project/pyarrow) if you want Parquet I/O features that preserve metadata in the hopper

## Features

- **DataFrame-Level Expression Management**: Store multiple Polars **expressions** on a DataFrame via the `.hopper` namespace.
- **Apply When Ready**: Each expression is automatically applied once the DataFrame has all columns required by that expression.
- **Namespace Plugin**: Access everything through `df.hopper.*(...)`—no subclassing or monkey-patching.
- **Metadata Preservation**: Transformations called through `df.hopper.<method>()` keep the same expression hopper on the new DataFrame.
- **No Central Orchestration**: Avoid fiddly pipeline step names or schemas—just attach your expressions once, and they get applied in the right order automatically.
- **Optional Serialisation**: If you want to store or share expressions across runs (e.g., Parquet round-trip), you can serialise them to JSON or binary and restore them later—without forcing overhead in normal usage.

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
#  - This one is valid right away: pl.col("user_id") != 0
#  - Another needs a future 'age' column
df.hopper.add_filters(pl.col("user_id") != 0)
df.hopper.add_filters(pl.col("age") > 18)  # 'age' doesn't exist yet

# Apply what we can; the first expression is immediately valid:
df = df.hopper.apply_ready_filters()
print(df)
# Rows with user_id=0 are dropped.

# Now let's do a transformation that adds an 'age' column.
# By calling df.hopper.with_columns(...), the plugin
# automatically copies the hopper metadata to the new DataFrame.
df2 = df.hopper.with_columns(
    pl.Series("age", [25, 15, 30])  # new column
)

# Now the second expression can be applied:
df2 = df2.hopper.apply_ready_filters()
print(df2)
# Only rows with age > 18 remain. That expression is then removed from the hopper.
```

### How It Works

Internally, **polars-expr-hopper** attaches a small “manager” object (a plugin namespace) to each `DataFrame`. This manager leverages [polars-config-meta](https://pypi.org/project/polars-config-meta/) to store data in `df.config_meta.get_metadata()`, keyed by the `id(df)`.

1. **List of In-Memory Expressions**:
   - Maintains a `hopper_filters` list of Polars expressions (`pl.Expr`) in the DataFrame’s metadata.
   - Avoids Python callables or lambdas so that **.meta.root_names()** can be used for schema checks and optional serialisation is possible.

2. **Automatic Column Check** (`apply_ready_filters()`)
   - On `apply_ready_filters()`, each expression’s required columns (via `.meta.root_names()`) are compared to the current DataFrame schema.
   - Expressions referencing missing columns remain pending.
   - Expressions referencing all present columns are applied via `df.filter(expr)`.
   - Successfully applied expressions are removed from the hopper.

3. **Metadata Preservation**
   - Because we rely on **polars-config-meta**, transformations called through `df.hopper.select(...)`, `df.hopper.with_columns(...)`, etc. automatically copy the same `hopper_filters` list to the new DataFrame.
   - This ensures **pending** expressions remain valid throughout your pipeline until their columns finally appear.

4. **No Monkey-Patching**
   - Polars’ plugin system is used, so there is no monkey-patching of core Polars classes.
   - The plugin registers a `.hopper` namespace—just like `df.config_meta`, but specialised for expression management.

Together, these features allow you to:

- store a **set** of Polars expressions in one place
- apply them **as soon as** their required columns exist
- easily carry them forward through the pipeline

All without global orchestration or repeated expression checks.

This was motivated by wanting a way to make a flexible CLI tool and express filters for the results
at different steps, without a proliferation of CLI flags. From there, the idea of a 'queue' which
was pulled from on demand, in FIFO order but on the condition that the schema must be amenable was born.

This idea **could be extended to `select` statements**, but initially filtering was the primary deliverable.

### API Methods

- `add_filters(*exprs: tuple[pl.Expr, ...])`
  Add a new predicate (lambda, function, Polars expression, etc.) to the hopper.

- `apply_ready_filters() -> pl.DataFrame`
  Check each stored expression’s root names. If the columns exist, `df.filter(expr)` is applied. Successfully applied expressions are removed.
- `list_filters() -> List[pl.Expr]`
  Inspect the still-pending expressions in the hopper.
- `serialise_filters(format="binary"|"json") -> List[str|bytes]`
  Convert expressions to JSON strings or binary bytes.
- `deserialise_filters(serialised_list, format="binary"|"json")`
  Re-create in-memory `pl.Expr` objects from the serialised data, overwriting any existing expressions.

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
