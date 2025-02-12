---
title: "Get Started"
icon: material/human-greeting
---

# Getting Started

## 1. Installation

`polars-filter-hopper` is [on PyPI](https://pypi.org/project/polars-filter-hopper). Install with:

```bash
pip install polars-filter-hopper[polars]
```

!!! info "Using `uv` (optional)"
    If you set up [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended for a smoother developer experience), you can install with:
    ```bash
    uv pip install polars-filter-hopper[polars]
    ```
    or set up a project (e.g., `uv init --app --package`, `uv venv`, then activate the venv), and add `polars-filter-hopper`:
    ```bash
    uv add polars-filter-hopper[polars]
    ```

## 2. Usage

`polars-filter-hopper` provides a CLI tool called `polars_hopper`. To list a user’s GitHub repositories:

```bash
polars_hopper my-username
```

To apply filters or walk files instead of list repos, add flags. For example:

```bash
polars_hopper my-username -w --filter '{name}.str.startswith("d3")'
```

This will list only files from repositories whose name starts with `"d3"`.

### More CLI Examples

- **List repos with a name filter**:
  ```bash
  polars_hopper my-username -f '{name}.str.contains("demo")'
  ```
- **List files non-recursively**:
  ```bash
  polars_hopper my-username -w
  ```
- **List all files, output to CSV**:
  ```bash
  polars_hopper my-username -w -output-format csv
  ```

For advanced usage like limiting rows/columns, see the [CLI reference](index.md).

## 3. Local Development

1. **Clone the Repo**:
   ```bash
   git clone https://github.com/lmmx/polars-filter-hopper.git
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
   This automatically runs lint checks (e.g., black, flake8) before each commit.

4. **Run Tests** (if applicable):
   ```bash
   pytest
   ```
5. **Build/Serve Docs** (if included):
   ```bash
   mkdocs serve
   ```
   Then visit the local server link. Use `mkdocs gh-deploy` to publish on GitHub Pages.

## 4. Example Workflow

1. **List Repositories**:
   ```bash
   polars_hopper octo-user
   ```
2. **Apply a Filter**:
   ```bash
   polars_hopper octo-user --filter='{name}.str.startswith("demo")'
   ```
3. **Switch to Files**:
   ```bash
   polars_hopper octo-user --walk
   ```
4. **Combine Steps**:
   ```bash
   polars_hopper octo-user -F --filter='pl.col("file_path").str.contains(".md")'
   ```
   This filters file trees in each repository for Markdown files.

## 5. Configuration

`polars-filter-hopper` primarily relies on:
- **`GITHUB_TOKEN`**: Recommended to avoid low rate limits, if not set it will try to use [`gh`][gh].
- **Caching**: By default, it caches your repos in a user-specific cache directory.
- **CLI Flags**: Control recursion, output format, table dimensions, and more via flags:
  - `--rows`, `--cols`, `--short`: Manage table display size.
  - `--filter`: Apply a Polars-based filter or DSL expression.

[gh]: https://cli.github.com/

For further details, consult the [API Reference](api/index.md) or the help text:

```bash
polars_hopper --help
```
