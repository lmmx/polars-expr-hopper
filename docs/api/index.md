# API Reference

Welcome to the API Reference for **polars-filter-hopper**!

Below, you'll find documentation for the library’s primary modules and classes. These pages are
generated from the source code and include details on function signatures, class methods, and
parameters used throughout the project. If you're looking for a deeper understanding of how
**polars-filter-hopper** retrieves and filters GitHub data using Polars, you’ve come to the right place.

Use the navigation panel on the left to explore each module. You’ll see how to:
- Initialize and configure an `Inventory` for GitHub repositories,
- Apply filters using Polars expressions or DSL syntax (`{column}.str.startswith("foo")`),
- Recursively list and inspect files in repos,
- Cache results to speed up repeated calls,
- And more!

If you’re new to the project, start with the main [Get Started](../get_started.md) guide to see
installation instructions and CLI usage examples. After that, you can return here for a thorough,
module-by-module breakdown of the **polars-filter-hopper** codebase.
