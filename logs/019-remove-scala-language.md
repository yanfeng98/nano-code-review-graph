# 019 — Remove Scala (scala) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed Scala (`.scala`) language support from the parser and downstream
consumers. `.scala` files are no longer detected as source code. Scala had no
dedicated resolver modules, helper functions, or data-constant entries — its
handling was entirely inline across the four node-type mapping tables, two
condition branches (`_get_bases`, `_extract_import`), one dead-code branch
(`instance_expression` in `_get_call_name`), and the notebook `%scala` magic.
Scala was the last language depending on the JVM ecosystem, so the
`.gradle/**` and `*.jar` ignore patterns were also removed. The
`tree-sitter-scala` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently,
so the removal is at the code/mapping layer only.

## Changes

### Core code (2 files)
- **`code_review_graph/parser.py`**:
  - Removed `".scala": "scala"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"scala"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `class_definition`/`enum_definition`/`import_declaration`/`call_expression`/
    `generic_function` preserved for gdscript/TS/Solidity/Go/Rust etc.)
  - Removed the `_get_bases` Scala branch (`extends_clause` base extraction)
  - Removed the `_extract_import` Scala branch (`import_declaration` parsing)
  - Removed the dead `instance_expression` branch in `_get_call_name`
    (its only trigger was Scala's `_CALL_TYPES` entry)
  - Removed `"%scala"` from the notebook `skip_magics` set
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no scala entries — untouched
- **`code_review_graph/incremental.py`**: Deleted the Gradle/JAR ignore
  patterns (`**/.gradle/**`, `*.jar`) — Scala was the last language relying on
  the JVM ecosystem

### Tests (3 files edited + 2 fixtures)
- **`tests/test_multilang.py`**: Deleted `TestScalaParsing` class
  (6 test methods: language detection, classes/traits/objects, functions,
  imports, inheritance, calls)
- **`tests/test_notebook.py`**: Deleted `test_skips_scala_cells`; changed
  `test_non_python_kernel` to use a Julia kernel example; updated
  `test_cell_index_tracking` (`process_results` cell index 6 → 5 after the
  `%scala` cell was removed)
- **`tests/test_incremental.py`**: Removed the `.gradle`/`*.jar` assertions
  from `test_should_ignore_framework_defaults` (DEFAULT-dependent) and updated
  the docstring; the nested-dependency test with an explicit pattern list is
  unaffected
- **`tests/fixtures/sample.scala`**: Deleted
- **`tests/fixtures/sample_databricks_notebook.ipynb`**: Removed the `%scala`
  cell (8 → 7 cells)

### Documentation
- **`README.md`**: Removed `Scala` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Scala` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Scala` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Scala` from languages section
- **`skills/build-graph/SKILL.md`**: Removed `Scala` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Backend group removed `Scala`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (scala grammar bundled in wheel,
  cannot be uninstalled separately)
- **`_get_call_name`** shared `generic_function` handling (Rust uses it)
- **`pyproject.toml`** ruff exclude comment (notebook fixture, no Scala code)
- **`CHANGELOG.md`** and other historical records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` and `incremental.py` import cleanly; zero
  `scala`/`%scala`/`.gradle`/`*.jar` references remain in `code_review_graph/`
  (except shared `generic_function`/`scalar`/`escalate` substrings)
- 454 tests passed in edited files (notebook, incremental, multilang)
- Zero `Scala`/`scala`/`%scala` references in docs
- Diagram source regenerated
