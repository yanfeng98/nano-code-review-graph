# 037 — Remove Zig (zig) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Zig (`.zig`) language support from the parser and downstream consumers.
`.zig` files are no longer detected as source code. Zig was a dedicated parser
(similar to Nix): all four node-type tables had empty `"zig": []` entries (the
generic walker never handled zig directly), and everything was dispatched
through `_extract_zig_constructs` from `_extract_from_tree`. Its implementation
was a 6-function + 1-constant helper section (`_ZIG_CONTAINER_KINDS`,
`_extract_zig_constructs` handling VarDecl/Decl/TestDecl →
`_handle_zig_fn_decl`/`_handle_zig_var_decl`/`_handle_zig_test_decl`/
`_zig_extract_import_target`/`_extract_zig_calls_in_subtree`), the dispatch
gate, and a `_do_resolve_module` zig branch (`@import("./foo.zig")` relative-path
resolution). Shared helpers (`_is_test_function`/`_qualify`/
`_resolve_module_to_file`/`_do_resolve_module`/`_extract_from_tree`) are
retained. The `tree-sitter-zig` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".zig": "zig"` from `EXTENSION_TO_LANGUAGE`
  - Removed the four `"zig": []` node-type table entries with their comments
    (`_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES`)
  - Removed the `# --- Zig-specific constructs ---` dispatch gate in
    `_extract_from_tree` (Bash block above, Verilog block below retained)
  - Deleted the Zig helpers section (6 functions + `_ZIG_CONTAINER_KINDS`)
  - Removed the `_do_resolve_module` zig branch; bash/python/js branches retained
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    zig; shared helpers untouched

### Tests (2 files edited + 2 fixtures deleted)
- **`tests/test_multilang.py`**: Deleted `TestZigParsing` (12 test methods:
  language detection, top-level functions, struct methods,
  struct/enum/union classes (`zig_kind`), imports, calls, @intCast builtin calls,
  @import not a call, test block → Test node, in-source test TESTED_BY,
  qualified method calls, nodes language)
- **`tests/test_parser_load_probe.py`**: Replaced the 4 `"zig"` probe-language
  placeholders with `verilog` (probe test logic unchanged)
- **`tests/fixtures/sample_zig.zig`**: Deleted
- **`tests/fixtures/sample_zig_util.zig`**: Deleted

### Documentation
- **`README.md`**: Removed `Zig` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Zig` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Zig` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Zig` from languages section
- **`diagrams/generate_diagrams.py`**: Systems group `["C", "C++", "Zig"]` →
  `["C", "C++"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (zig grammar bundled in wheel)
- Shared helpers (`_is_test_function`/`_qualify`/`_resolve_module_to_file`/
  `_do_resolve_module`/`_extract_from_tree`)
- **`docs/MAINTAINER_RECONCILIATION_2026-07-17.md`** (historical notes),
  **`token_benchmark.py`**/**`agent_baseline.py`** (no `.zig`), **`skills/`**
  (no Zig)
- **`CHANGELOG.md`** (historical Zig entries), **`.serena/project.yml`**
  (comment token), `code-review-graph-vscode/` (`JZig` hash false positive)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `zig`/`Zig`/`.zig`/
  `_zig_`/`_ZIG_`/`_extract_zig`/`zig_kind` references remain in
  `code_review_graph/` and `tests/`
- 232 tests passed in `test_parser_load_probe.py` + `test_multilang.py` +
  `test_parser.py`
- Full suite: 1755 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Zig` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.zig"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- `_do_resolve_module` other-language branches retained:
  `TestBashParsing`/`TestCParsing`/`TestVerilogParsing` pass
