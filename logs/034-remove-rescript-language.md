# 034 — Remove ReScript (rescript) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed ReScript (`.res`/`.resi`) language support from the parser and
downstream consumers. `.res`/`.resi` files are no longer detected as source
code. ReScript was a self-contained regex-based fallback parser (no bundled
tree-sitter grammar), like VB.NET: it had **no entries** in the four node-type
tables and no shebang mapping. Both `.res` (implementation) and `.resi`
(interface) mapped to `"rescript"`, with interface files flagged via
`extra["rescript_interface"]`. Its implementation was a module-level
ReScript regex/helper block (`_RESCRIPT_*` constants + `_strip_rescript_noise`/
`_rescript_brace_depth_array`/`_scan_rescript_modules`), the `.res`/`.resi`
test-file patterns, the `parse_bytes` dispatch, and the large `_parse_rescript`
method (modules/let-bindings/externals/types/open/JSX). Cross-module resolution
lived in a standalone `rescript_resolver.py` wired into `incremental.py`.

The removal is at the code/mapping layer only (no grammar dependency to
uninstall).

## Changes

### Core code (3 files)
- **`code_review_graph/parser.py`**:
  - Removed `".res"`/`".resi"` from `EXTENSION_TO_LANGUAGE` and the two
    `.*_test\.resi?$` / `.*\.test\.resi?$` entries from `_TEST_FILE_PATTERNS`
  - Deleted the module-level `# ReScript regex patterns and helpers` section
    (12 `_RESCRIPT_*` constants + 3 helpers)
  - Removed the `parse_bytes` ReScript dispatch branch
  - Deleted the `_parse_rescript` method (~384 lines)
  - `_builtin_language_names()` derives from the mappings — auto-excludes
    rescript; shared helpers (`_is_test_file`/`_is_test_function`/`_qualify`/
    `_resolve_call_targets`/`normalize_file_path`) untouched
- **`code_review_graph/rescript_resolver.py`**: Deleted (207 lines,
  `resolve_rescript_cross_module`)
- **`code_review_graph/incremental.py`**: Deleted `_run_rescript_resolver` and
  the `"rescript_resolution"` stat key from `full_build`, identity-rebuild,
  and `incremental_update` return dicts, plus the `rescript_changed` update
  logic
- **`code_review_graph/scoped_resolver.py`**: Updated docstring that referenced
  "in the same style as the ReScript resolver"

### Tests (1 file edited + 2 fixtures deleted)
- **`tests/test_multilang.py`**: Deleted 4 ReScript test classes:
  `TestRescriptParser` (14 methods), `TestRescriptInterfaceParser` (5),
  `TestRescriptEdgeCases` (7), `TestRescriptCrossModuleResolver` (6)
- **`tests/fixtures/sample.res`**: Deleted (79 lines)
- **`tests/fixtures/sample.resi`**: Deleted (27 lines)

### Documentation
- **`README.md`**: Removed `ReScript` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `ReScript` from supported-languages list
- **`docs/FEATURES.md`**: Removed `ReScript` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `ReScript` from languages section
- **`diagrams/generate_diagrams.py`**: Other group `["ReScript", "Jupyter/.ipynb"]`
  → `["Jupyter/.ipynb"]`; footer text dropped "ReScript regex pass";
  regenerated `.excalidraw` sources

### Not changed
- Shared helpers (`_is_test_file`/`_is_test_function`/`_qualify`/
  `_resolve_call_targets`/`normalize_file_path`)
- **`token_benchmark.py`**/**`agent_baseline.py`** (no `.res`/`.resi`),
  **`skills/`** (no ReScript), **`.serena/project.yml`** (no rescript)
- **`CHANGELOG.md`** (historical "ReScript support" entry),
  `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `rescript`/`ReScript`/
  `.res`/`.resi`/`_rescript_`/`_RESCRIPT_` references remain in
  `code_review_graph/` and `tests/`
- 254 tests passed in `test_multilang.py` + `test_parser.py`
- Full suite: 1785 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `ReScript` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.res"))`/`x.resi` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
