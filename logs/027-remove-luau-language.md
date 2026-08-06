# 027 — Remove Luau (luau) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Luau (`.luau`, Roblox's Lua variant) language support from the parser
and downstream consumers. `.luau` files are no longer detected as source code.
**Lua (`.lua`) is retained.** Luau shared the entire Lua code path: the
`_extract_lua_constructs` family (parser.py L6611-6887:
`_extract_lua_constructs`/`_handle_lua_variable_declaration`/
`_handle_lua_table_function`/`_lua_get_require_target`) is used by both Lua and
Luau and contains **no** `language == "luau"` branch — it only passes `language`
through — so those functions stay untouched for Lua. Luau's only differences
from Lua were one extra `_CLASS_TYPES` entry (`"luau": ["type_definition"]`),
an `.luau` extension mapping, and three `language in ("lua", "luau")` gate
tuples. The `tree-sitter-luau` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".luau": "luau"` from `EXTENSION_TO_LANGUAGE` (`.lua` kept)
  - Removed `"luau"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (Lua keys kept; shared node-type strings
    `function_declaration`/`function_call` remain for Lua, `type_definition`
    remains for C)
  - Changed three `if language in ("lua", "luau")` gate tuples to
    `if language == "lua"`: `_extract_from_tree` Lua-constructs dispatch,
    `_get_name` function_declaration method-name extraction, `_get_call_name`
    dot/method_index_expression call-name extraction
  - Updated comments referencing "Lua/Luau" → "Lua" (4 places: the dispatch
    block header, `_get_name`, `_get_call_name`, and the `_IMPORT_TYPES` note)
  - `_builtin_language_names()` derives from the mappings/tables — auto-excludes
    luau; `_extract_lua_constructs` family and shared helpers
    (`_resolve_module_to_file`/`_get_params`/`_qualify`/`_is_test_function`)
    untouched for Lua

### Tests (1 file edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestLuauParsing` (14 test methods:
  language detection, type_aliases→classes, top-level functions,
  variable-assigned functions, dot/colon syntax methods, inherited table
  methods, imports, calls, contains, method parent names, test functions,
  node language, calls inside methods). `TestLuaParsing` kept — the two classes
  shared no fixtures (sample.lua/sample.luau are independent)
- **`tests/fixtures/sample.luau`**: Deleted (`sample.lua` kept)

### Documentation ("Lua/Luau" → "Lua")
- **`README.md`**: Removed `/Luau` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `/Luau` from supported-languages list
- **`docs/FEATURES.md`**: Removed `/Luau` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `/Luau` from languages section

### Not changed
- **`tree-sitter-language-pack`** dependency (luau grammar bundled in wheel,
  cannot be uninstalled separately)
- **`_extract_lua_constructs` family** (Lua retained — must stay)
- **`diagrams/generate_diagrams.py`** (Scripting group already lists only
  `Lua`, not `Luau`), **`skills/`** (no Lua/Luau mentions),
  **`token_benchmark.py`**/**`agent_baseline.py`** (never contained `.luau`,
  verified against content and git history)
- **`CHANGELOG.md`** (historical Luau-support entry; Lua-support entry),
  **`.serena/project.yml`** (comment-only lua server list)
- `code-review-graph-vscode/`, `sample.lua` fixture, `TestLuaParsing`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `luau`/`Luau`/`.luau`
  references remain in `code_review_graph/` and `tests/`
- 368 tests passed in `test_multilang.py` + `test_parser.py`
- Full suite: 1943 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Luau` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.luau"))` → None;
  `detect_language(Path("x.lua"))` → `"lua"`; Lua constructs (require, table
  OOP, method calls) still parse — verified by `TestLuaParsing`
