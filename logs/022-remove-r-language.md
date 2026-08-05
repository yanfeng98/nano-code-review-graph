# 022 — Remove R (r) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed R (`.r`/`.R`) language support from the parser and downstream
consumers. `.r`/`.R` files are no longer detected as source code. R was the
second most complex removal (after PHP): it had 8 dedicated functions across
two regions (`_extract_r_constructs` dispatcher and the R-specific
helpers/handlers), 6 condition branches, and notebook `%r` magic support.
R was the only dual-kernel notebook language (`supported = {"python", "r"}`);
after removal, notebooks are Python-only. The `tree-sitter-r` grammar remains
bundled inside `tree-sitter-language-pack` (a single wheel with ~170
grammars) and cannot be uninstalled independently, so the removal is at the
code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".r": "r"` from `EXTENSION_TO_LANGUAGE` and `"Rscript": "r"` from
    the shebang map
  - Removed `"r"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`, `_IMPORT_TYPES`,
    `_CALL_TYPES` (shared node-type strings like `call`/`function_definition`
    preserved for other languages)
  - Deleted `_extract_r_constructs` and the R-specific helpers/handlers region
    (`_r_call_func_name`/`_r_first_string_arg`/`_r_iter_args`/
    `_r_find_named_arg`/`_handle_r_binary_operator`/`_handle_r_call`/
    `_handle_r_class_call`/`_extract_r_methods`)
  - Removed 6 condition branches: `_extract_from_tree` R dispatch,
    `_collect_file_scope` (`name <- function` defined-names), `_extract_import`
    (library/require/source), and 3 notebook branches (`supported` set,
    `%pip`/`!` line filter, cell-language gate)
  - Removed notebook `%r` magic from both `magic_lang_map` dicts and the
    `namespace_operator` dead-code branch in `_get_call_name`
  - Removed R test-file patterns (`test[_-].*.[rR]$`, `tests/testthat/`)
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no r entries — untouched
- **Notebook behavior change**: `supported = {"python", "r"}` → `{"python"}`;
  R-kernel notebooks are now skipped entirely. Python-only.

### Fixtures (2 deleted + 2 edited)
- **Deleted**: `tests/fixtures/sample.R`, `tests/fixtures/test_sample.R`
- **`tests/fixtures/sample_databricks_notebook.ipynb`**: Removed the `%r` cell
  (7 → 6 cells)
- **`tests/fixtures/sample_databricks_export.py`**: Removed the `%r` cell block
  (kept the COMMAND separator between `%sql` and `%md` to avoid chunk merging)

### Tests (3 files edited)
- **`tests/test_multilang.py`**: Deleted `TestRParsing` class (9 test methods)
- **`tests/test_parser.py`**: Deleted `test_r_top_level_call_attributes_to_file`
  (virtual `module_scope_sample.R` path, no fixture)
- **`tests/test_notebook.py`**: Deleted `TestRKernelNotebook` (3 methods);
  updated Databricks cell-count assertions (3→2 for both notebook and export
  fixtures) and cell-index assertions (`process_results` 5→4,
  `process_events` 4→3 after the `%r` cell was removed); changed the
  `test_conflicting_kernel_metadata` fallback language `"r"` → `"julia"`

### Documentation
- **`README.md`**: Removed `R` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `R` from supported-languages list and
  `Rscript` from the interpreter list
- **`docs/FEATURES.md`**: Removed `R` from parser-surface list (kept historical
  v2.0.0 "Added Dart, R, Perl" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `R` from languages section
- **`diagrams/generate_diagrams.py`**: Scripting group removed `R`;
  regenerated `.excalidraw` sources (the `def R(...)` rectangle helper is
  unrelated and kept)
- **`pyproject.toml`**: Updated the ruff-exclude comment
  (`# SQL/R/Scala cells` → `# SQL cells`)

### Not changed
- **`tree-sitter-language-pack`** dependency (r grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings (`call`/`function_definition`)
- `b'R"'` C/C++ raw-string prefix and the diagrams `R(...)` rectangle helper
- **`CHANGELOG.md`**, `docs/FEATURES.md` v2.0.0, `docs/ROADMAP.md` historical
  entries, `.serena`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `"r"`/`Rscript`/
  `_extract_r_`/`_handle_r_`/`namespace_operator`/`testthat`/`%r` references
  remain in `code_review_graph/` (except unrelated substrings like
  `_ansible_extract_role`/`_extract_rust`)
- 44 tests passed in `test_notebook.py`; 478 tests passed across the edited
  files
- Zero `R`/`Rscript` references in docs (except historical records)
- Diagram source regenerated
