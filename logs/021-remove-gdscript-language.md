# 021 — Remove GDScript (gdscript) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed GDScript (`.gd`) language support from the parser and downstream
consumers. `.gd` files are no longer detected as source code. GDScript had no
dedicated resolver modules, helper functions, or data-constant entries — its
handling was inline across the four node-type mapping tables and one
`_extract_import` condition branch (which treated `extends` statements as
imports). The `tree-sitter-gdscript` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".gd": "gdscript"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"gdscript"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `class_definition`/`function_definition`/`call` preserved for
    python/C/C++/etc.; gdscript-only `class_name_statement`/`extends_statement`/
    `attribute_call` removed), plus their comment blocks
  - Removed the `_extract_import` gdscript branch (GDScript `extends`
    statements as imports), preserving the custom-language branch that follows
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no gdscript entries — untouched

### Tests (1 file edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestGDScriptParsing` class
  (11 test methods: language detection, class_name statement, inner class,
  top-level functions, inner class methods, extends-as-import, direct calls,
  attribute calls, internal call resolution, contains edges)
- **`tests/fixtures/sample.gd`**: Deleted

### Documentation
- **`README.md`**: Removed `GDScript` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `GDScript` from supported-languages list
- **`docs/FEATURES.md`**: Removed `GDScript` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `GDScript` from languages section
- **`diagrams/generate_diagrams.py`**: Domain group removed `GDScript`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (gdscript grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings (`class_definition`/`function_definition`/`call`)
- `tools/build.py` "Godot builds" performance comment and
  `test_tools.py` "Godot hang" comment (Godot engine performance notes, not
  GDScript language support)
- **`CHANGELOG.md`** and other historical records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `gdscript`/`GDScript`/
  `.gd` references remain in `code_review_graph/` (except Godot performance
  comments in build.py/test_tools.py)
- 293 tests passed in `test_multilang.py`
- Zero `GDScript`/`gdscript` references in docs
- Diagram source regenerated
