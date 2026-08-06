# 030 — Remove SQL (sql) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed SQL (`.sql`) language support from the parser and downstream consumers.
`.sql` files are no longer detected as source code. SQL was a dedicated parser
(dispatched via `_parse_sql`, never through the generic `_extract_from_tree`
walker): it had **no entries** in the four node-type tables (`"sql": []`), no
shebang mapping, and used tree-sitter for CREATE TABLE/VIEW/FUNCTION plus a
regex fallback for CREATE PROCEDURE. Its implementation was a module-level
`_SQL_TABLE_RE`/`_SQL_KEYWORDS`/`_DBT_REF_RE` plus a SQL-parser class section
(`_parse_sql`, `_walk_sql_tree`, `_extract_sql_ddl`, and three dbt methods
`_is_dbt_model_path`/`_dbt_model_paths`/`_extract_dbt_model`).

**User decisions:**
- **Notebook SQL cells retained** — `%sql`/`# MAGIC %sql` cell table-reference
  extraction (using the shared `_SQL_TABLE_RE` regex to emit IMPORTS_FROM) is a
  notebook-independent feature that never calls the SQL language parser.
  `_SQL_TABLE_RE`, the notebook `%sql`/`# MAGIC %sql` magic maps, and the
  `if lang == "sql"` branch in `_parse_notebook_cells` are kept;
  `test_notebook.py` still passes.
- **dbt fully removed** — the dbt model extraction is a SQL-language sub-path
  (only reachable from `_parse_sql`, depends on the `.sql` extension). With SQL
  removed it loses its entry point, so `_is_dbt_model_path`/`_dbt_model_paths`/
  `_extract_dbt_model` and `_DBT_REF_RE` are deleted along with
  `test_dbt_parser.py`.

The `tree-sitter-sql` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".sql": "sql"` from `EXTENSION_TO_LANGUAGE`
  - Removed the four `"sql": []` node-type table entries with their comments
    (`_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES`)
  - Deleted `_DBT_REF_RE` (dbt) and `_SQL_KEYWORDS` (table-reference filter);
    **kept `_SQL_TABLE_RE`** for notebook SQL-cell extraction
  - Removed the `parse_bytes` SQL dispatch branch and its comment
  - Deleted the whole `# SQL parser` section (~317 lines): `_SQL_PROC_RE`,
    `_SQL_DDL_NODE_TYPES`, `_parse_sql`, `_is_dbt_model_path`,
    `_dbt_model_paths`, `_extract_dbt_model`, `_walk_sql_tree`,
    `_extract_sql_ddl`
  - Removed the `_dbt_model_paths_cache` instance attribute (only used by
    `_dbt_model_paths`)
  - Retained notebook SQL-cell handling: `%sql`/`# MAGIC %sql` magic maps and
    the `if lang == "sql"` table-reference branch in `_parse_notebook_cells`
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    sql; shared helpers (`normalize_file_path`/`_is_test_file`/`_get_parser`)
    untouched

### Tests (1 file edited, 1 file + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestSQLParsing` (9 test methods:
  language detection, file node, tables, view, function, procedure, contains,
  table-reference edges)
- **`tests/test_dbt_parser.py`**: **Deleted** (dbt-specific, ~19 assertions on
  `sql_kind`/language)
- **`tests/fixtures/sample.sql`**: Deleted (sole `.sql` fixture)
- **`tests/test_notebook.py`**: **Retained** (notebook SQL-cell extraction kept;
  `_SQL_TABLE_RE` import and `TestSqlTableExtraction` continue to pass)

### Documentation
- **`README.md`**: Removed `SQL` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `SQL` from supported-languages list
- **`docs/FEATURES.md`**: Removed `SQL` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `SQL` from languages section
- **`CLAUDE.md`**: `test_multilang.py` description dropped `SQL`
- **`diagrams/generate_diagrams.py`**: Domain group `["SQL", "Verilog", "Nix"]`
  → `["Verilog", "Nix"]`; regenerated `.excalidraw` sources

### Not changed
- **Notebook SQL-cell extraction** (`_SQL_TABLE_RE`, `%sql`/`# MAGIC %sql` maps)
  — user decision to retain
- **`"sql"` risk keyword** in `constants.py`/`tools/build.py` (security-scoring
  keyword, not a language definition)
- **`tree-sitter-language-pack`** dependency (sql grammar bundled in wheel)
- Shared helpers (`normalize_file_path`/`_is_test_file`/`_get_parser`)
- **`CHANGELOG.md`** (historical SQL-support and notebook SQL-cells entries),
  `.serena/project.yml`, `code-review-graph-vscode/`
- SQLite engine paths (`BFS_ENGINE`, graph store, sqlite3) — SQLite, not the
  SQL language

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `sql`/`SQL`/`.sql`/
  `_parse_sql`/`_SQL_PROC`/`_SQL_DDL`/`_SQL_KEYWORDS`/`_DBT_`/`_dbt_`/`sql_kind`
  references remain in `code_review_graph/` and `tests/` (only notebook
  SQL-cell + SQLite paths, both retained)
- 390 tests passed in `test_multilang.py` + `test_notebook.py` +
  `test_parser.py` (notebook SQL-cell tests included)
- Full suite: 1909 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `SQL` references in docs (except historical records and SQLite)
- End-to-end: `detect_language(Path("x.sql"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- Notebook SQL-cell extraction still works (`test_notebook.py` passes)
