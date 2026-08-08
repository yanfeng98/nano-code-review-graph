# 033 — Remove Julia (julia) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Julia (`.jl`) language support from the parser and downstream
consumers. `.jl` files are no longer detected as source code. Julia was the
most complex removal so far: it is not an isolated fallback parser but is
deeply embedded in the shared tree-sitter walker. It had four non-empty
node-type table entries (struct/abstract/module definitions, function/macro
definitions, import/using statements, call/broadcast/macrocall expressions), a
16-member dedicated function set (`_extract_julia_constructs` — a large method
handling const aliases, short-form functions, signatures, include/export/
public, @enum/@testset macrocalls — plus `_resolve_julia_call_targets`,
`_collect_julia_scoped_import_names`, and 13 `_julia_*` helpers), and 13
`if language == "julia"` branches embedded in shared methods
(`_extract_classes`/`_extract_functions`/`_extract_calls`/`_get_name`/
`_get_bases`/`_extract_import`/`_get_call_name`/`_resolve_call_targets`/
`_resolve_call_target`/`_collect_file_scope`/`_collect_import_names`/
`_extract_from_tree`), plus the `.jl` test-file patterns. Shared node-type
strings (`import_statement`/`call_expression`/`function_definition`) remain for
other languages; the cpp/verilog shared tuples `("julia", "cpp")`/`("verilog",
"julia")` were narrowed to cpp/verilog only.

**User decisions:**
- **superpowers Julia docs deleted** — `docs/superpowers/plans/2026-07-17-julia-parser-reconciliation.md`
  and `docs/superpowers/specs/2026-07-17-julia-parser-reconciliation-design.md`
- **notebook julia kernel removed** — the 3 julia kernel-metadata spots in
  `test_notebook.py` were switched to `go` (test intent preserved)

The `tree-sitter-julia` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".jl": "julia"` from `EXTENSION_TO_LANGUAGE` and the two
    `test/runtests.jl` / `test/.*.jl` entries from `_TEST_FILE_PATTERNS`
  - Removed the four `"julia"` node-type table entries with their comments
    (`_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES`)
  - Deleted the `# Julia-specific helpers` section (13 `_julia_*` helpers) and
    `_extract_julia_constructs` (~593 lines)
  - Deleted `_resolve_julia_call_targets` and `_collect_julia_scoped_import_names`
  - Removed 13 julia branches embedded in shared methods; narrowed
    `("julia", "cpp")` → `"cpp"` and `("verilog", "julia")` → `"verilog"`
  - Removed julia-specific extra keys (`julia_module_qualifier`,
    `julia_qualified_def`, `julia_call_module`, `julia_kind`,
    `julia_export`/`julia_public`) — now dead code
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    julia; shared helpers and cpp/verilog/js/ts/python paths untouched

### Tests (2 files edited, 2 files + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestJuliaParsing` (24 test methods)
- **`tests/test_julia_reconciliation.py`**: **Deleted** (21 tests)
- **`tests/fixtures/sample.jl`**: Deleted
- **`tests/test_notebook.py`**: Switched the 3 julia kernel-metadata references
  to `go` (non-python-kernel test intent preserved) — user decision
- **`tests/test_windows_path_identity.py`**: Deleted
  `test_julia_identity_uses_forward_slashes_for_windows_paths`; the
  `_qualify` path-normalization test now uses `.py` paths

### Documentation
- **`README.md`**: Removed `Julia` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Julia` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Julia` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Julia` from languages section
- **`docs/superpowers/plans/2026-07-17-julia-parser-reconciliation.md`**:
  **Deleted** (user decision)
- **`docs/superpowers/specs/2026-07-17-julia-parser-reconciliation-design.md`**:
  **Deleted** (user decision)
- **`diagrams/generate_diagrams.py`**: Removed the `Scripting` group (its only
  language was Julia); regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (julia grammar bundled in wheel)
- Shared node-type strings (`import_statement`/`call_expression`/
  `function_definition`) and shared helpers
- **`token_benchmark.py`**/**`agent_baseline.py`** (no `.jl`), **`skills/`**
  (no Julia), **`.serena/project.yml`** (comment token, kept by convention)
- **`CHANGELOG.md`** (historical: PHP/Laravel+Julia entry, Julia improvements,
  "4 new languages"), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `julia`/`Julia`/`.jl`/
  `_julia_`/`_extract_julia`/`julia_*` references remain in `code_review_graph/`
  and `tests/`
- 342 tests passed in `test_multilang.py` + `test_notebook.py` +
  `test_windows_path_identity.py` + `test_parser.py`
- Full suite: 1817 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Julia` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.jl"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- cpp/verilog shared branches retained: `TestCParsing`/`TestCppParsing`/
  `TestVerilogParsing` pass
