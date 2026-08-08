# 036 — Remove Nix (nix) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Nix (`.nix`) language support from the parser and downstream consumers.
`.nix` files are no longer detected as source code. Nix was a flake-aware
parser: all four node-type tables had empty `"nix": []` entries (the generic
walker never handled nix directly), and everything was dispatched through
`_extract_nix_constructs` from `_extract_from_tree`. Its implementation was a
5-function dedicated set (`_extract_nix_constructs` handling `attrpath = expr;`
bindings → Function nodes, flake `inputs.*.url` → IMPORTS_FROM, and
`import`/`callPackage` → IMPORTS_FROM; plus `_is_nix_flake_file`/
`_nix_attrpath_parts`/`_extract_nix_flake_input_urls`/
`_extract_nix_import_targets`), the dispatch gate, and a `_do_resolve_module`
nix branch. Shared helpers (`_qualify`/`_resolve_module_to_file`/
`_extract_from_tree`) are retained. The `tree-sitter-nix` grammar remains
bundled inside `tree-sitter-language-pack` (a single wheel with ~170 grammars)
and cannot be uninstalled independently, so the removal is at the code/mapping
layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".nix": "nix"` from `EXTENSION_TO_LANGUAGE`
  - Removed the four `"nix": []` node-type table entries with their comments
    (`_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES`)
  - Removed the `# --- Nix-specific constructs ---` dispatch gate in
    `_extract_from_tree` (bash block above, verilog block below retained)
  - Deleted the 5-function Nix section (`_is_nix_flake_file`/
    `_nix_attrpath_parts`/`_extract_nix_flake_input_urls`/
    `_extract_nix_import_targets`/`_extract_nix_constructs`)
  - Removed the `_do_resolve_module` nix branch (relative-path file resolve);
    bash/zig/python/js branches retained
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    nix; shared helpers untouched

### Tests (1 file edited + 2 fixtures deleted)
- **`tests/test_multilang.py`**: Deleted `TestNixParsing` (7 test methods:
  language detection, nodes language, top-level bindings→functions, flake
  inputs→IMPORTS_FROM, import/callPackage→IMPORTS_FROM, non-flake has no input
  edges, CONTAINS)
- **`tests/fixtures/sample.nix`**: Deleted (flake fixture)
- **`tests/fixtures/sample_module.nix`**: Deleted
- `test_parser.py`/`test_custom_languages.py`: no Nix references, unchanged

### Documentation
- **`README.md`**: Removed `Nix` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Nix` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Nix` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Nix` from languages section
- **`diagrams/generate_diagrams.py`**: Domain group `["Verilog", "Nix"]` →
  `["Verilog"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (nix grammar bundled in wheel)
- Shared helpers (`_qualify`/`_resolve_module_to_file`/`_extract_from_tree`)
- **`docs/MAINTAINER_RECONCILIATION_2026-07-17.md`** (historical note),
  **`token_benchmark.py`**/**`agent_baseline.py`** (no `.nix`), **`skills/`**
  (no Nix)
- **`CHANGELOG.md`** (historical "Nix support (flake-aware)" entry),
  **`.serena/project.yml`** (comment token), `code-review-graph-vscode/`,
  Unix false positives

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `nix`/`Nix`/`.nix`/
  `_nix_`/`_extract_nix`/`flake.nix` references remain in `code_review_graph/`
  and `tests/`
- 237 tests passed in `test_multilang.py` + `test_parser.py`
- Full suite: 1767 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Nix` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.nix"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- `_do_resolve_module` other-language branches retained:
  `TestBashParsing`/`TestZigParsing`/`TestVerilogParsing` pass
