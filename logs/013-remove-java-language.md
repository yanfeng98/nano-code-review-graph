# 013 — Remove Java (java) Language Support

**Date:** 2026-08-03
**Branch:** 260802-v2.3.7

## Summary

Removed Java (`.java`) language support from the parser, all downstream graph
consumers, and every Java-only framework enrichment: Spring DI, Spring Event,
Spring Config, Spring Scheduling, Spring WebFlux, Kafka, and Temporal. The three
post-build resolvers (`spring_resolver.py`, `event_resolver.py`,
`temporal_resolver.py`) and the Spring config-key helper (`config_keys.py`) were
deleted. `.java` files are no longer detected as source code. The
`tree-sitter-java` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (11 files)
- **`code_review_graph/parser.py`**:
  - Removed `".java": "java"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"java"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES`
  - Deleted ~35 Java/Spring/Temporal/Kafka helper functions (region
    `_get_java_annotations` → `_emit_kafka_edges_from_method`), including
    `_get_java_method_and_receiver`
  - Removed JUnit tokens (`ParameterizedTest`, `RepeatedTest`, `TestFactory`,
    `org.junit.Test`, `org.junit.jupiter.api.Test`) from `_TEST_ANNOTATIONS`;
    kept `Test` (shared by Kotlin/PHP) and Rust entries
  - Deleted all Spring/Temporal/Kafka constants
    (`_SPRING_STEREOTYPE_ANNOTATIONS`, `_SPRING_INJECT_ANNOTATIONS`,
    `_TEMPORAL_*`, `_KAFKA_*`, `_SPRING_SCHEDULED_ANNOTATIONS`,
    `_SPRING_EVENT_*`, `_JAVA_PACKAGE_KEY`, `_SPRING_REQUEST_PREFIX_KEY`,
    `_SPRING_REQUEST_MAPPINGS`, `_SPRING_WEBFLUX_HTTP_VERBS`)
  - Removed the `spring_config` language detection and dispatch; deleted the
    Spring config parser section (`_parse_spring_config`/`_parse_spring_yaml`/
    `_parse_spring_properties` and helpers)
  - Removed 22 `language == "java"` branches (typed bindings, extract classes/
    functions/calls, member-call receiver, import-map package capture, import
    collection, module resolution, `_get_name`, `_get_bases`, `_extract_import`,
    `_get_call_name`)
  - Changed `("java", "kotlin")` import tuple → `"kotlin"`
  - Removed `"java"` from `_TYPED_CALL_LANGUAGES`, `block_types`,
    `parameter_types`, and `.*Test\.java$` from `_TEST_FILE_PATTERNS`
  - Refactored `_extract_classes` to the shared `_modifier_annotation_names`
    path (Kotlin annotation persistence preserved)
  - Removed `from .config_keys import ...` import
- **Deleted modules**: `code_review_graph/spring_resolver.py`,
  `code_review_graph/event_resolver.py`, `code_review_graph/temporal_resolver.py`,
  `code_review_graph/config_keys.py`
- **`code_review_graph/incremental.py`**: Removed `_run_spring_resolver`/
  `_run_spring_event_resolver`/`_run_temporal_resolver` wrappers, their
  full-build and incremental-build calls, the `spring_changed` gate, and the
  `spring_resolution`/`event_resolution`/`temporal_resolution` stats keys.
  Kept `.gradle/**` and `*.jar` ignore patterns (Kotlin/Scala JVM ecosystem).
- **`code_review_graph/graph.py`**: Removed `get_config_consumers` (only caller
  was query's `consumers_of`)
- **`code_review_graph/tools/query.py`**: Removed `consumers_of` pattern and
  handler, the Java FQN resolution helpers (`_java_fqn_candidates`,
  `_looks_like_java_method_fqn`), and the `config_keys` import
- **`code_review_graph/main.py`**: Removed `consumers_of` from query command docs
- **`code_review_graph/flows.py`**: Removed Java Spring/Temporal entry-point
  patterns (`GetMapping`/`Scheduled`/`KafkaListener`/`WorkflowMethod`, etc.);
  kept Kotlin, JS/TS, Android patterns
- **`code_review_graph/token_benchmark.py`**, **`eval/benchmarks/agent_baseline.py`**:
  Removed `.java` from source-extension tuples
- **`code_review_graph/refactor.py`**: Comment update only
- **Comment cleanup** (post-review sweep): removed remaining `Java` mentions
  from source comments in `parser.py` (Swift `_FUNCTION_TYPES` note, PHP
  resolver mirror note, custom-name heuristic note, Java/Kotlin modifiers
  comment), `incremental.py` (Gradle ignore note), and `scoped_resolver.py`
  (resolver-style note); kept generic "Doxygen/Javadoc-style" and JavaScript
  references

### Tests (8 files deleted + 6 edited)
- **Deleted**: `test_java_call_references.py`, `test_spring_java_reconciliation.py`,
  `test_spring_scheduling.py`, `test_spring_events.py`, `test_spring_endpoints.py`,
  `test_spring_webflux_endpoints.py`, `test_spring_config.py`, `test_status_stats.py`
- **`tests/test_multilang.py`**: Deleted `TestJavaParsing`,
  `TestJavaImportResolution`, `TestSpringDIParsing`, `TestSpringDIResolver`,
  `TestTemporalParsing`, `TestTemporalResolver`, `TestKafkaParsing`; removed
  `Java` from module docstring
- **`tests/test_parser.py`**: Deleted `test_junit_annotation_marks_test`; comment
- **`tests/test_docstring_embeddings.py`**: Deleted two javadoc tests (Java-only)
- **`tests/test_flows.py`**: Deleted `test_detect_entry_points_spring_scheduled`
- **`tests/test_parser_load_probe.py`**: Probe language `"java"` → `"go"`
- **`tests/test_agent_transparency.py`**: Deleted 3 Java FQN tests
- **`tests/test_typed_receiver_calls.py`**: Deleted
  `test_java_generic_parameter_local_and_field_types_resolve`
- **`tests/test_incremental.py`**: Updated "# Gradle/Java" comment → "# Gradle"

### Fixtures (4 deleted, 1 kept)
- **Deleted**: `SampleJava.java`, `SpringDI.java`, `TemporalWorkflow.java`,
  `KafkaPatterns.java`
- **Kept**: `sample.kt` (Kotlin; its `import java.util.UUID` is a JDK package
  name reference, not Java-language support)

### Documentation
- **`README.md`**: Removed `Java` from language lists (2 places)
- **`docs/FEATURES.md`**: Removed `Java` from parser-surface list and
  "Go, Rust, Java verified" → "Go, Rust verified"
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Java` from languages section
- **`docs/USAGE.md`**: Removed `Java` from supported-languages list
- **`docs/schema.md`**: `(Java, TypeScript, Go)` → `(TypeScript, Go)`;
  INJECTS reworded without Java/Spring; removed TEMPORAL_STUB entry and marked
  INJECTS / CONSUMES / PRODUCES as reserved edge kinds with no current producer
- **`docs/CUSTOM_LANGUAGES.md`**: Removed "(Spring, Temporal)" from the
  no-framework-annotations note
- **`skills/build-graph/SKILL.md`**: Removed `Java` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Removed `Java` from Backend group;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-java`** dependency in `uv.lock` / `pyproject.toml`: transitive
  via `tree-sitter-language-pack`, cannot be uninstalled separately
- **`.gradle/**` and `*.jar`** ignore patterns: Kotlin/Scala JVM ecosystem
- **`tests/test_custom_languages.py`** `grammar = "java"` test: custom-language
  loader loads the grammar independently, nodes carry `java_custom` not `java`
- **`CHANGELOG.md`**, `docs/MAINTAINER_RECONCILIATION_2026-07-17.md`: history
- **`.serena/project.yml`**: external tool config
- **`code-review-graph-vscode/`**: no Java references

## Verification
- All core modules import cleanly
- 597 tests passed in edited files (multilang, parser, docstrings, flows, probe,
  agent transparency, typed receivers)
- 138 tests passed (incremental + custom languages, including `grammar="java"`)
- Zero `java` references remain in `code_review_graph/` (verified by grep)
- Zero standalone `Java` references in docs (word-boundary grep)
- Diagram source regenerated (88 elements in coverage diagram)
