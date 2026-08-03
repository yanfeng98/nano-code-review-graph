# 012 — Remove C# (csharp) Language Support

**Date:** 2026-08-03
**Branch:** 260802-v2.3.7

## Summary

Removed C# (`.cs`) language support from the parser and all downstream graph
consumers. `.cs` files are no longer detected as source code; C#-specific
node-type mappings, typed-call resolution, namespace-based import/impact
fallbacks, and scoped-call disambiguation were deleted. The `tree-sitter-c-sharp`
grammar remains bundled inside `tree-sitter-language-pack` (a single wheel with
~170 grammars) and cannot be uninstalled independently, so the removal is at the
code/mapping layer only — the dependency is left untouched.

## Changes

### Core code (5 files)
- **`code_review_graph/parser.py`**:
  - Removed `".cs": "csharp"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"csharp"` entries from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES`
  - Deleted `_CSHARP_SUMMARY_RE`, `_csharp_attribute_names()`,
    `_csharp_namespaces()`, `_get_csharp_receiver_method()`
  - Removed 13 `language == "csharp"` branches (docstring summary, file-node
    namespace capture, typed-call collection, typed bindings, method-target
    resolution, class/function attribute collection, member-call receiver,
    `_get_name`, `_get_bases`, `_extract_import`)
  - Removed `"csharp"` from `_TYPED_CALL_LANGUAGES`, `block_types`,
    `parameter_types`
  - Changed `("java", "csharp")` import tuple → `"java"`
- **`code_review_graph/scoped_resolver.py`**:
  - Removed `"csharp"` from `_SCOPED_LANGUAGES` and `_RECEIVER_SCOPE_LANGUAGES`
  - Deleted `csharp_namespaces_by_file` data build, `csharp_disambiguate()`,
    and the csharp parse-target / dispatch branches
  - Trimmed module docstring (PHP/Rust only)
- **`code_review_graph/graph.py`**:
  - Removed C# `using X.Y;` namespace-import fallback block
  - Removed csharp namespace bridge seeds from `_impact_seed_qns()`
- **`code_review_graph/incremental.py`**:
  - Changed scoped-resolver trigger `(".php", ".rs", ".cs")` → `(".php", ".rs")`
- **`code_review_graph/tools/query.py`**:
  - Removed `importers_of` C# namespace fallback block

### Tests (3 files + 1 fixture)
- **`tests/test_multilang.py`**:
  - Deleted `_has_csharp_parser()` helper and 6 C# test classes:
    `TestCSharpParsing`, `TestCSharpMethodNames`, `TestCSharpAttributes`,
    `TestCSharpNamespaceResolution`, `TestCSharpReceiverCallResolution`,
    `TestCSharpNamespaceImpactAndCoverage`
  - Removed `C#` from module docstring and PHP-test class docstring
- **`tests/test_docstring_embeddings.py`**:
  - Deleted `test_csharp_xml_summary_crosses_attribute`
- **`tests/test_parser.py`**: Removed `C#` from a docstring comment
- **`tests/fixtures/Sample.cs`**: Deleted

### Documentation
- **`README.md`**: Removed `C#` from language list (2 places)
- **`docs/FEATURES.md`**: Removed `C#` from parser-surface feature list
- **`docs/USAGE.md`**: Removed `C#` from supported-languages list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `C#` from languages section
- **`docs/schema.md`**: `(Java, C#, TypeScript, Go)` → `(Java, TypeScript, Go)`
- **`skills/build-graph/SKILL.md`**: Removed `C#` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Removed `C#` from Systems group
- i18n READMEs: already removed

### Not changed
- **`tree-sitter-c-sharp`** dependency in `uv.lock` / `pyproject.toml`:
  transitive via `tree-sitter-language-pack`, cannot be uninstalled separately
- **`CHANGELOG.md`**, `docs/MAINTAINER_RECONCILIATION_2026-07-17.md`:
  historical records
- **`docs/FEATURES.md`** historical line "Renamed language identifier from
  `c_sharp` to `csharp`": kept as history
- **`.serena/project.yml`**: external tool config, not runtime logic
- **`code-review-graph-vscode/`**: no C# references

## Verification
- Full build: 259 files, 5055 nodes, 41527 edges (all other languages intact)
- A repo containing only `Test.cs` builds to 0 files / 0 nodes (C# no longer
  detected)
- `code-review-graph status` no longer lists `csharp` (33 languages remain)
- 2257 tests passed (2 pre-existing documentation-test failures unrelated to
  this change, caused by the earlier Hindi README removal)
- Ruff lint: all checks passed
- Zero `csharp` / `C#` references in Python files and updated docs
