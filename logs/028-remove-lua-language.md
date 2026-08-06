# 028 — Remove Lua (lua) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Lua (`.lua`) language support from the parser and downstream
consumers. `.lua` files are no longer detected as source code. Unlike Luau
(removed last round), Lua is a first-class language with a dedicated
construct-extraction family of 4 functions in parser.py:
`_extract_lua_constructs` (dispatches variable_declaration /
function_declaration / top-level function_call), `_handle_lua_variable_declaration`
(`local x = require(...)` → IMPORTS_FROM; `local fn = function() end` →
Function), `_handle_lua_table_function` (`function Animal.new()` /
`Animal:speak()` → Function with table parent), and `_lua_get_require_target`
(module-path extraction). These call shared helpers (`_is_test_function`,
`_qualify`, `_get_params`, `_resolve_module_to_file`, `_extract_from_tree`)
which are retained. The `tree-sitter-lua` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".lua": "lua"` from `EXTENSION_TO_LANGUAGE`
  - Removed `# Lua` comment + `"lua": "lua"` from
    `SHEBANG_INTERPRETER_TO_LANGUAGE`
  - Removed `"lua"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared string `function_declaration`
    remains for JS/TS/TSX/Go/Verilog; `function_call` string remains for
    `_HCL_RECURSE_TYPES` but is no longer any language's call node type)
  - Deleted the whole `# Lua-specific helpers` block (4 functions,
    ~278 lines): `_extract_lua_constructs`, `_handle_lua_variable_declaration`,
    `_handle_lua_table_function`, `_lua_get_require_target`
  - Removed 3 `if language == "lua"` branches: `_extract_from_tree` dispatch
    gate, `_get_name` function_declaration method-name extraction,
    `_get_call_name` dot/method_index_expression call-name extraction
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    lua; `_TYPED_CALL_LANGUAGES`/`block_types`/`parameter_types` had no lua
    entries; `_extract_import` never had a lua branch (require went through
    `_extract_lua_constructs`); shared helpers and `_extract_imports`/`_extract_import`
    untouched

### Tests (1 file edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestLuaParsing` (15 test methods:
  language detection, top-level functions, variable-assigned functions,
  dot/colon syntax methods, inherited table methods, imports, calls, contains,
  method parent names, test functions, params, node language, calls inside
  methods). Module docstring does not mention Lua
- **`tests/fixtures/sample.lua`**: Deleted (140-line fixture, sole `.lua` file)

### Documentation
- **`README.md`**: Removed `Lua` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Lua` from supported-languages list; removed
  `Lua` from shebang interpreter list
- **`docs/FEATURES.md`**: Removed `Lua` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Lua` from languages section
- **`diagrams/generate_diagrams.py`**: Scripting domain group `["Lua", "Julia"]`
  → `["Julia"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (lua grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared helpers (`_is_test_function`/`_qualify`/`_get_params`/
  `_resolve_module_to_file`/`_extract_from_tree`) and shared node-type strings
  (`function_declaration` for JS/TS/TSX/Go/Verilog; `function_call` in
  `_HCL_RECURSE_TYPES`)
- **`token_benchmark.py`**/**`agent_baseline.py`** (never contained `.lua`,
  independently re-verified), **`CHANGELOG.md`** (historical Lua and Luau
  support entries), **`.serena/project.yml`** (comment-only lua server list)
- `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `lua`/`Lua`/`.lua`
  references remain in `code_review_graph/` and `tests/` (only "evaluate"
  substrings, false positives)
- 386 tests passed in `test_multilang.py` + `test_parser.py` +
  `test_custom_languages.py`
- Full suite: 1929 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Lua` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.lua"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
