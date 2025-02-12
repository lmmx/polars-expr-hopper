---
title: "Get Started"
icon: material/human-greeting
---

# Getting Started

## 1. Installation

**polars-expr-hopper** is [on PyPI](https://pypi.org/project/polars-expr-hopper). To install with standard Polars support:

```bash
pip install polars-expr-hopper[polars]
```

!!! info "Using `uv` (optional)"
    If you prefer to use [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended for a smoother developer experience), you can install with:
    ```bash
    uv pip install polars-expr-hopper[polars]
    ```
    or set up a project (e.g., `uv init --app --package`, `uv venv`, then activate the venv), and add **polars-expr-hopper**:
    ```bash
    uv add polars-expr-hopper[polars]
    ```

## 2. Usage

**polars-expr-hopper** provides a Polars plugin that attaches a `.hopper` namespace to your DataFrame. Within this namespace, you can add, list, and apply **Polars expressions** (`pl.Expr`). The plugin automatically preserves your expressions across transforms like `df.hopper.select(...)` or `df.hopper.with_columns(...)`, applying them as soon as the needed columns appear.

### Basic Example

```python
import polars as pl
import polars_expr_hopper  # registers .hopper plugin

# Create an initial DataFrame
df = pl.DataFrame({
    "user_id": [1, 2, 3, 0],
    "name": ["Alice", "Bob", "Charlie", "NullUser"],
})

# Add an expression referencing 'user_id'
df.hopper.add_filters(pl.col("user_id") != 0)

# Apply what we can; 'user_id' is present, so the filter applies now
df = df.hopper.apply_ready_filters()
print(df)
# Rows with user_id=0 are dropped.

# Add an expression referencing 'age' (not yet present)
df.hopper.add_filters(pl.col("age") > 18)

# Add the 'age' column
df2 = df.hopper.with_columns(pl.Series("age", [25, 15, 30]))

# Now apply again; only rows with age>18 remain
df2 = df2.hopper.apply_ready_filters()
print(df2)
```

If you need **optional serialization** (e.g., to store expressions in Parquet or share them across sessions), see the [API reference](api/index.md) for methods like `serialize_filters()` and `deserialize_filters()`.

## 3. Local Development

1. **Clone the Repo**:
   ```bash
   git clone https://github.com/lmmx/polars-expr-hopper.git
   ```
2. **Install Dependencies**:
   - If you’re using [pdm](https://pdm.fming.dev/latest/):
     ```bash
     pdm install
     ```
   - Otherwise, standard pip:
     ```bash
     pip install -e .
     ```
3. **Optional: Pre-commit Hooks**:
   ```bash
   pre-commit install
   ```
   This runs lint checks (e.g., ruff, black) before each commit.
4. **Run Tests**:
   ```bash
   pytest
   ```
5. **Build/Serve Docs** (if included):
   ```bash
   mkdocs serve
   ```
   Then visit the local server link. Use `mkdocs gh-deploy` to publish on GitHub Pages.

## 4. Example Workflow

1. **Create or load a DataFrame** with Polars:
   ```python
   df = pl.DataFrame({"col": [1, 2, 3, 4]})
   ```
2. **Add expressions referencing columns**:
   ```python
   df.hopper.add_filter(pl.col("col") > 2)
   ```
3. **Apply**:
   ```python
   df2 = df.hopper.apply_ready_filters()
   # Rows with col <= 2 are dropped
   ```
4. **Add new columns** or transformations**:
   ```python
   df3 = df2.hopper.with_columns(pl.Series("extra_col", [10, 20]))
   # The plugin's metadata is copied forward
   ```
5. **Re-apply** if you have pending expressions referencing `extra_col`:
   ```python
   df3 = df3.hopper.apply_ready_filters()
   ```

## 5. Configuration

**polars-expr-hopper** primarily relies on Polars’ existing ecosystem. There is no specific environment variable or external config required.

- If you plan to **serialize** expressions for Parquet or across sessions, note that Polars warns it may not be stable across major Polars versions.
- If you see any “missing column” errors, remember the plugin only applies expressions once all required columns exist. You can check pending expressions via:
  ```python
  df.hopper.list_filters()
  ```

To learn more, see the [API Reference](api/index.md) or ask in [Issues](https://github.com/lmmx/polars-expr-hopper/issues).
