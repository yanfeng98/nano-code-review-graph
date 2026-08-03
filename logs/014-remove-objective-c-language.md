# 014 — Remove Objective-C (objc) Language Support

**Date:** 2026-08-03
**Branch:** 260802-v2.3.7

## Summary

Removed Objective-C (`.m`) language support from the parser and downstream
consumers. `.m` files are no longer detected as source code. Unlike the C#
and Java removals, Objective-C had no dedicated resolver modules or helper
functions — its handling was entirely inline in `_get_name()` and
`_get_call_name()`, plus the four node-type mapping tables. The
`tree-sitter-objc` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently,
so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".m": "objc"` from `EXTENSION_TO_LANGUAGE` (kept `.h` → C and
    `.hpp`/`.hh` → C++ mappings, plus the `.h` C/C++ shared-header comment)
  - Removed `"objc"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (with their comments)
  - **`_get_name()`**: changed shared tuple `("c", "cpp", "objc")` →
    `("c", "cpp")` and updated the comment (C/C++ preserved); removed the
    `objc method_definition` name branch
  - **`_get_call_name()`**: removed the `objc message_expression` call-name
    branch
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types` already had no
    objc entries — untouched

### Tests (2 files edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestObjectiveCParsing` class
  (8 test methods: language detection, class/interface, instance/class
  methods, C `main`, imports, message-expression calls)
- **`tests/test_tools.py`**: `TestQueryGraphCallTargetFallbacks` seed data
  relabeled from `.m`/`objc` → `.ts`/`typescript` (arbitrary language tag;
  query-fallback test logic unchanged, tests still pass)
- **`tests/fixtures/sample.m`**: Deleted

### Documentation
- **`README.md`**: Removed `Objective-C` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Objective-C` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Objective-C` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Objective-C` from languages
  section
- **`diagrams/generate_diagrams.py`**: Systems group
  `["C", "C++", "Objective-C", "Zig"]` → `["C", "C++", "Zig"]`; regenerated
  `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (objc grammar bundled in wheel,
  cannot be uninstalled separately)
- **`tests/test_cpp_qt_headers.py`** `"objective_c.h"` (C-header
  disambiguation test; filename is wordplay, content is C syntax — unrelated
  to ObjC support)
- **`communities.py`** `objective_function="modularity"` (Leiden clustering
  objective parameter, unrelated to Objective-C)
- **`CHANGELOG.md`** and other historical records
- **`.serena/project.yml`**, `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `objc` references remain
- 481 tests passed in edited files (multilang + tools)
- Zero `Objective-C`/`objc` references in docs (word-boundary grep)
- Diagram source regenerated
