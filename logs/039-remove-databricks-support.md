# 039 — Remove Databricks notebook Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Databricks notebook support from the parser and downstream consumers.
Databricks is not a language but a notebook format: `.py` exports that begin
with a `# Databricks notebook source` header, split into cells by
`# COMMAND ----------` delimiters, with `# MAGIC %sql`/`%md`/`%sh` magic lines.
Detection happened entirely inside `parse_bytes` (`.py` files always detect as
`"python"`; the first-line header check routed them to
`_parse_databricks_py_notebook`). The coupling to ordinary Jupyter notebooks
is small and one-way: `_parse_databricks_py_notebook` calls the shared
`_parse_notebook_cells`, so removing it leaves `_parse_notebook`/
`_parse_notebook_cells`/`CellInfo`/`_SQL_TABLE_RE` intact — **ordinary Jupyter
notebooks (including `%sql` cells) are unaffected.** Databricks never affected
`_builtin_language_names()` (`.py` files stayed `"python"`).

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed the `parse_bytes` Databricks detection branch (first-line
    `# Databricks notebook source` check, incl. CRLF handling — issue #239)
  - Deleted `_parse_databricks_py_notebook` (~97 lines): header strip,
    `# COMMAND` cell splitting, `# MAGIC %sql`/`%md`/`%sh` handling,
    `notebook_format="databricks_py"` tagging, `_parse_notebook_cells` call
  - Updated a `find_dead_code` comment that referenced "Jupyter/Databricks
    notebook cells"
  - Retained `_parse_notebook`/`_parse_notebook_cells`/`CellInfo`/`_SQL_TABLE_RE`

### Tests (1 file edited)
- **`tests/test_notebook.py`**:
  - Deleted `TestDatabricksNotebookParsing` (7 methods) and
    `TestDatabricksPyNotebook` (12 methods, incl. #239 CRLF/LF and
    false-positive regression tests)
  - Deleted `TestNotebookEdgeCases.test_databricks_header_not_on_line_1` and
    `test_databricks_py_no_command_delimiters`
  - **Renamed** `test_empty_databricks_cells` → `test_empty_magic_cells`
    (the test constructs a plain Jupyter nbformat dict — it tests `%pip`/`!`
    line filtering, not Databricks)
  - Retained `TestNotebookParsing`, `TestSqlTableExtraction`, and the other
    `TestNotebookEdgeCases` tests (plain Jupyter)

### Fixtures + config
- **`tests/fixtures/sample_databricks_export.py`**: Deleted
- **`tests/fixtures/sample_databricks_notebook.ipynb`**: Deleted
- **`tests/fixtures/sample_notebook.ipynb`**: Retained (plain Jupyter)
- **`pyproject.toml`**: Removed the two Databricks fixture entries from ruff
  `exclude` and `per-file-ignores`

### Documentation
- **`README.md`**: `Jupyter/Databricks` → `Jupyter` (3 places incl. img alt)
- **`docs/USAGE.md`**: `Jupyter/Databricks notebooks` → `Jupyter notebooks`
- **`docs/FEATURES.md`**: `Jupyter/Databricks notebooks` → `Jupyter notebooks`
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: `Jupyter/Databricks notebooks` →
  `Jupyter notebooks`
- **`diagrams/generate_diagrams.py`**: footer text dropped "Databricks";
  regenerated `.excalidraw` sources

### Not changed
- Ordinary Jupyter notebook support (`_parse_notebook`/`_parse_notebook_cells`/
  `CellInfo`/`_SQL_TABLE_RE`)
- **`CHANGELOG.md`** (historical "Databricks notebook parsing" entry),
  `.serena/project.yml` (no databricks), `code-review-graph-vscode/`
- `test_multilang.py`/`test_parser.py`/`test_custom_languages.py` (no
  Databricks references)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `databricks`/`Databricks`/
  `# MAGIC`/`notebook_format`/`databricks_py` references remain in
  `code_review_graph/` and `tests/`
- 25 tests passed in `test_notebook.py`
- Full suite: 1721 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Databricks` references in docs (except historical records)
- End-to-end: `sample_notebook.ipynb` still parses (Jupyter notebook intact);
  a Databricks `.py` export is now parsed as ordinary Python
