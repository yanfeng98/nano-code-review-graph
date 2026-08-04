# 016 — Remove Swift (swift) Language Support

**Date:** 2026-08-03
**Branch:** 260802-v2.3.7

## Summary

Removed Swift (`.swift`) language support from the parser and downstream
consumers. `.swift` files are no longer detected as source code. Swift had no
dedicated resolver modules, helper functions, or module-level constants — its
handling was entirely inline across the four node-type mapping tables and three
condition branches (`_extract_classes` for type-kind metadata, `_get_name` for
init/deinit/subscript and extension naming, `_get_bases` for inheritance). The
`tree-sitter-swift` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (3 files)
- **`code_review_graph/parser.py`**:
  - Removed `".swift": "swift"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"swift"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `class_declaration`/`import_declaration`/`call_expression`/`function_declaration`
    preserved for other languages; Swift-only `init_declaration`/
    `deinit_declaration`/`subscript_declaration`/`protocol_declaration` removed)
  - `_extract_classes`: removed the `if language == "swift":` block that stored
    `extra["swift_kind"]`; kept `extra: dict = {}` (used by decorators/docstring)
  - `_get_name`: removed the init/deinit/subscript naming branch and the
    extension `user_type` naming branch (Verilog branch preserved)
  - `_get_bases`: removed the `elif language == "swift":` inheritance branch
    (Julia branch preserved)
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` already had no swift entries — untouched
- **`code_review_graph/token_benchmark.py`**: Removed `.swift` from the
  source-extension tuple
- **`code_review_graph/eval/benchmarks/agent_baseline.py`**: Removed `.swift`
  from `_SOURCE_EXTS`

### Tests (1 file edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestSwiftParsing` class (15 test
  methods: language detection, classes, functions, enum, actor, extension,
  protocol, swift_kind metadata, inheritance, initializers, deinitializer,
  subscript); removed `Swift` from module docstring
- **`tests/fixtures/sample.swift`**: Deleted

### Documentation
- **`README.md`**: Removed `Swift` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Swift` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Swift` from parser-surface list (kept
  historical v1.6.2 name-extraction entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Swift` from languages section
- **`skills/build-graph/SKILL.md`**: Removed `Swift` from supported-languages
  list
- **`diagrams/generate_diagrams.py`**: Mobile group `["Swift", "Dart"]` →
  `["Dart"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (swift grammar bundled in wheel,
  cannot be uninstalled separately)
- **`docs/FEATURES.md`** v1.6.2 historical entry, `CHANGELOG.md` and other
  historical records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `swift` references remain
- 330 tests passed in `test_multilang.py`
- Zero `Swift`/`swift` references in docs (except historical FEATURES v1.6.2
  entry and CHANGELOG)
- Diagram source regenerated
