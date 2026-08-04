# 018 — Remove Dart (dart) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed Dart (`.dart`) language support from the parser and downstream
consumers. `.dart` files are no longer detected as source code. Dart had no
dedicated resolver modules or entry-point patterns, but carried two helpers
(`_extract_dart_calls_from_children` for call detection, `_find_dart_pubspec_root`
for `package:` URI resolution) and five condition branches. The
`tree-sitter-dart` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (3 files)
- **`code_review_graph/parser.py`**:
  - Removed `".dart": "dart"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"dart"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES` (shared `enum_declaration` preserved for TS/Solidity etc.;
    Dart-only `class_definition`/`mixin_declaration`/`function_signature`/
    `import_or_export` removed); `_CALL_TYPES` had no dart entry
  - Removed `re.compile(r".*_test\.dart$")` from `_TEST_FILE_PATTERNS`
  - Deleted `_extract_dart_calls_from_children` and `_find_dart_pubspec_root`
    (with the `_dart_pubspec_cache` init in `__init__`)
  - Removed 5 condition branches: `_extract_from_tree` Dart call detection,
    `_do_resolve_module` (`package:` URI + relative imports),
    `_get_name` (`function_signature`), `_get_bases` (superclass/mixins/
    interfaces), `_extract_import` (`import_or_export` recursive string)
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no dart entries — untouched
- **`code_review_graph/incremental.py`**: Deleted the Dart/Flutter ignore
  patterns (`**/.dart_tool/**`, `**/.pub-cache/**`)
- **`code_review_graph/tools/query.py`**: Updated the `inheritors_of` fallback
  comment (the INHERITS/IMPLEMENTS logic is generic and kept)

### Tests (3 files edited + 1 fixture deleted)
- **`tests/test_parser.py`**: Deleted the Dart test block (8 tests: language
  detection, file parse, imports, inheritance, contains edges, method parent,
  top-level function, call edges)
- **`tests/test_tools.py`**: Deleted
  `test_inheritors_of_bare_dart_class_ignores_member_matches` (issue #87)
- **`tests/test_incremental.py`**: Removed the Flutter/Dart assertion from
  `test_should_ignore_framework_defaults` and updated the docstring
- **`tests/fixtures/sample.dart`**: Deleted

### Documentation
- **`README.md`**: Removed `Dart` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Dart` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Dart` from parser-surface list (kept
  historical v2.0.0 "Added Dart, R, Perl" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Dart` from languages section
- **`diagrams/generate_diagrams.py`**: Deleted the Mobile group (its sole
  member `["Dart"]` is gone); updated the group-count comments; regenerated
  `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (dart grammar bundled in wheel,
  cannot be uninstalled separately)
- **`docs/FEATURES.md`** v2.0.0 and **`docs/ROADMAP.md`** historical entries
  ("Added Dart, R, Perl")
- **`query.py`** `inheritors_of` fallback code (generic, not Dart-specific)
- **`CHANGELOG.md`** and other historical records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`,
  `uv.lock` `cudart` (CUDA package, false positive)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `dart`/`pubspec`/`_dart_`
  references remain in `code_review_graph/`
- 387 tests passed in edited files (parser, tools, incremental)
- Zero `Dart`/`dart`/`pubspec` references in docs (except historical FEATURES
  v2.0.0 and ROADMAP entries)
- Diagram source regenerated
