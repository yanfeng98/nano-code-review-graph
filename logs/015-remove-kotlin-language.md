# 015 — Remove Kotlin (kotlin) Language Support

**Date:** 2026-08-03
**Branch:** 260802-v2.3.7

## Summary

Removed Kotlin (`.kt`/`.kts`) language support from the parser and downstream
consumers. `.kt` files are no longer detected as source code. Kotlin had no
dedicated resolver modules or helper functions — its handling was entirely
inline across the node-type mapping tables, typed-call analysis
(`_TYPED_CALL_LANGUAGES`/`block_types`/`parameter_types`), and six condition
branches (typed bindings, member-call receivers, file-scope imports, import
collection, module resolution, base classes). Kotlin-only entry-point
patterns in `flows.py` (`HiltViewModel`, `AndroidEntryPoint`, `Composable`)
were also removed. The `tree-sitter-kotlin` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (5 files)
- **`code_review_graph/parser.py`**:
  - Removed `".kt": "kotlin"` from `EXTENSION_TO_LANGUAGE` (no standalone
    `.kts` mapping existed)
  - Removed `"kotlin"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `class_declaration`/`call_expression` preserved for other languages)
  - Removed `re.compile(r".*Test\.kt$")` from `_TEST_FILE_PATTERNS` (kept
    `Test` in `_TEST_ANNOTATIONS` — used by PHP)
  - Removed `"kotlin"` from `_TYPED_CALL_LANGUAGES`, `block_types`,
    `parameter_types`
  - Removed 6 condition branches: `_typed_bindings_from_node`
    (class_parameter/parameter/variable_declaration),
    `_get_member_call_receiver_method` (navigation_expression),
    `_collect_file_scope` (import_list), `_collect_import_names`,
    `_do_resolve_module` (`.kt`/`.kts`), `_get_bases`
  - Updated Kotlin-specific comments in `_get_call_name` (kept shared
    `simple_identifier`/`navigation_expression` node-type handling — Verilog
    uses `simple_identifier`), `_modifier_annotation_names`, `_extract_classes`,
    `_extract_functions`
- **`code_review_graph/flows.py`**: Removed `Composable` from the Android
  lifecycle regex (kept `@Override`/`@OnLifecycleEvent`) and deleted the
  Kotlin coroutines / ViewModel regex
  (`(HiltViewModel|AndroidEntryPoint|Inject)`)
- **`code_review_graph/incremental.py`**: Updated `# Kotlin / Gradle` comment
  → `# Gradle` (kept `.gradle/**` and `*.jar` ignore patterns — Scala JVM
  ecosystem)
- **`code_review_graph/token_benchmark.py`**, **`eval/benchmarks/agent_baseline.py`**:
  Removed `.kt` from source-extension tuples

### Tests (3 files edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestKotlinParsing` and
  `TestKotlinAnnotations` classes; removed `Kotlin` from module docstring
- **`tests/test_parser.py`**: Deleted `test_kotlin_test_annotation_marks_test`
- **`tests/test_typed_receiver_calls.py`**: Deleted
  `test_kotlin_generic_parameter_local_and_field_types_resolve`
- **`tests/fixtures/sample.kt`**: Deleted

### Documentation
- **`README.md`**: Removed `Kotlin` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Kotlin` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Kotlin` from parser-surface list (kept
  historical v1.6.2 name-extraction entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Kotlin` from languages section
- **`skills/build-graph/SKILL.md`**: Removed `Kotlin` from supported-languages
  list
- **`diagrams/generate_diagrams.py`**: Mobile group `["Kotlin", "Swift", "Dart"]`
  → `["Swift", "Dart"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (kotlin grammar bundled in wheel,
  cannot be uninstalled separately)
- **`.gradle/**` and `*.jar`** ignore patterns (Scala JVM ecosystem)
- **`_get_call_name`** shared `simple_identifier`/`navigation_expression`
  node-type handling (Verilog uses `simple_identifier`)
- **`CHANGELOG.md`**, `docs/FEATURES.md` v1.6.2 historical entry, other
  historical records
- **`.serena/project.yml`**, `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `kotlin` references remain
- 511 tests passed in edited files (multilang + parser + typed receivers)
- Zero `Kotlin`/`kotlin` references in docs (except historical FEATURES v1.6.2
  entry and CHANGELOG)
- Diagram source regenerated
