# 024 — Remove Elixir (elixir) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Elixir (`.ex`/`.exs`) language support from the parser and downstream
consumers. `.ex`/`.exs` files are no longer detected as source code. Elixir had
four dedicated methods (`_elixir_call_identifier`,
`_elixir_module_name`, `_elixir_function_name_and_params`,
`_extract_elixir_constructs` handling defmodule/def/defp/alias/import/require/
use and ordinary call dispatch) plus one dispatch block in
`_extract_from_tree` and four empty node-type table entries
(`"elixir": []` in `_CLASS_TYPES`, `_FUNCTION_TYPES`, `_IMPORT_TYPES`,
`_CALL_TYPES`). The `tree-sitter-elixir` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".ex": "elixir"` and `".exs": "elixir"` from
    `EXTENSION_TO_LANGUAGE`
  - Removed `"elixir": []` keys (with their comment blocks) from
    `_CLASS_TYPES`, `_FUNCTION_TYPES`, `_IMPORT_TYPES`, `_CALL_TYPES`
  - Deleted the four Elixir-specific methods:
    `_elixir_call_identifier`, `_elixir_module_name`,
    `_elixir_function_name_and_params`, `_extract_elixir_constructs`
  - Removed the `# --- Elixir-specific constructs ---` dispatch block in
    `_extract_from_tree` (Nix dispatch now follows the Bash block directly)
  - `_extract_nix_constructs` docstring: "Bash/Elixir convention" →
    "Bash convention"
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no elixir entries — untouched
  - `_is_nix_flake_file` (shared) retained

### Tests (3 files edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestElixirParsing` class
  (7 test methods: language detection, nodes language, modules→classes,
  def/defp→functions with parent module, alias/import/require→imports,
  internal calls, CONTAINS edges)
- **`tests/test_parser.py`**: Deleted
  `test_elixir_top_level_dotted_call_attributes_to_file` (`.exs` script /
  mix-task module-scope `IO.puts`)
- **`tests/test_custom_languages.py`**: Removed the `app.ex` → `elixir`
  detection assertion (replaced with `app.ts` → `typescript`); updated the
  module docstring that referenced "only Elixir on the BEAM side"
- **`tests/fixtures/sample.ex`**: Deleted (sole `.ex` fixture;
  `module_scope_script.exs` was a virtual path with no fixture)

### Documentation
- **`README.md`**: Removed `Elixir` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Elixir` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Elixir` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Elixir` from languages
  section
- **`docs/CUSTOM_LANGUAGES.md`**: Updated `.ex`/`elixir` validation-rule
  examples to `.erl`/`typescript`
- **`diagrams/generate_diagrams.py`**: Backend domain group removed
  `Elixir`; regenerated `.excalidraw` sources (gitignored)

### Not changed
- **`tree-sitter-language-pack`** dependency (elixir grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings (`function_definition`/`call_expression` etc. used
  by TS/Verilog/C/etc.)
- **`CHANGELOG.md`, `docs/FEATURES.md` v1.x historical entry, other
  historical records**
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `elixir`/`Elixir`/
  `.ex`/`.exs` references remain in `code_review_graph/`
- 432 tests passed in `test_multilang.py` + `test_parser.py` +
  `test_custom_languages.py`; full suite: 1975 passed, 5 skipped
  (2 pre-existing `test_documentation.py` failures from a missing
  `README.hi-IN.md`, unrelated to this change)
- Zero `Elixir` references in docs (except historical records)
- Diagram source regenerated
- End-to-end: a mixed repo with `.ex`/`.exs` + `.py`/`.rs` files parses
  `.ex`/`.exs` as 0 nodes while Python/Rust still parse normally
- Self-audit (3 rounds) found and fixed one formatting regression: the
  `TestElixirParsing` deletion left 3 blank lines in `test_multilang.py`
  (PEP8 wants 2); fixed, 250 tests still pass
