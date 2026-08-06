# 029 — Remove VB.NET (vbnet) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed VB.NET (`.vb`) language support from the parser and downstream
consumers. `.vb` files are no longer detected as source code. VB.NET is a
self-contained "bounded structural fallback" parser: `tree-sitter-language-pack`
does not bundle a Visual Basic grammar, so VB.NET never went through the
tree-sitter walker — it had **no entries** in the four node-type tables and no
shebang mapping. Its entire implementation was concentrated in four regions:
the `.vb` extension mapping, a module-level regex/helper section (~250 lines of
`_VBNET_*` constants incl. `_VBNET_CALL_KEYWORDS` and 8 `_vbnet_*` helper
functions), a `parse_bytes` dispatch branch, and two class methods
`_parse_vbnet` (namespaces/types/members via regex, Imports→IMPORTS_FROM,
Inherits/Implements→INHERITS/IMPLEMENTS, calls, TESTED_BY) plus
`_resolve_vbnet_edges` (case-insensitive same-file target resolution). All
`_VBNET_*`/`_vbnet_*` symbols were internal-only; shared helpers
(`normalize_file_path`/`_is_test_file`/`_is_test_function`/`_qualify`/`NodeInfo`/
`EdgeInfo`) are retained.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".vb": "vbnet"` from `EXTENSION_TO_LANGUAGE` + the two comment
    lines above it (VB.NET is not a bundled grammar)
  - Deleted the whole `# VB.NET regex patterns and helpers` module section
    (~250 lines): `_VBNET_IDENT`/`_VBNET_DOTTED_IDENT`/`_VBNET_MODIFIER_WORDS`/
    `_VBNET_MODIFIER_RE`/`_VBNET_IMPORT_RE`/`_VBNET_NAMESPACE_RE`/
    `_VBNET_END_NAMESPACE_RE`/`_VBNET_TYPE_RE`/`_VBNET_END_TYPE_RE`/
    `_VBNET_MEMBER_RE`/`_VBNET_OPERATOR_RE`/`_VBNET_END_MEMBER_RE`/
    `_VBNET_INHERITS_RE`/`_VBNET_IMPLEMENTS_RE`/`_VBNET_NEW_RE`/`_VBNET_CALL_RE`/
    `_VBNET_CALL_KEYWORDS` + helpers `_vbnet_normalize_name`/`_strip_vbnet_noise`/
    `_vbnet_logical_lines`/`_vbnet_parenthesized`/`_vbnet_split_top_level`/
    `_vbnet_type_parameters`/`_vbnet_signature_parts`/`_vbnet_relationship_targets`
  - Removed the `parse_bytes` dispatch branch
    (`if language == "vbnet": return self._parse_vbnet(...)`) and its comment;
    the ReScript dispatch (adjacent) is retained
  - Deleted the `# VB.NET: bounded structural fallback` section with
    `_parse_vbnet` and `_resolve_vbnet_edges` (~420 lines)
  - `_builtin_language_names()` derives from `EXTENSION_TO_LANGUAGE.values()` —
    auto-excludes vbnet; the four node-type tables never had a vbnet key;
    `_TYPED_CALL_LANGUAGES`/`block_types`/`parameter_types` had no vbnet entries

### Tests (1 file edited)
- **`tests/test_language_reconciliation.py`**: Deleted `TestVBNetReconciliation`
  (3 test methods: namespaces/generics/multiline signatures scoping,
  case-insensitive relationships/calls resolution to graph nodes, overloads
  sharing one stable graph symbol)
- `test_multilang.py`/`test_parser.py`/`test_custom_languages.py` unchanged (no
  VB references); no `.vb` fixture existed

### Documentation
- **`README.md`**: Removed `VB.NET` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `VB.NET` from supported-languages list
- **`docs/FEATURES.md`**: Removed `VB.NET` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `VB.NET` from languages section

### Not changed
- Shared helpers (`normalize_file_path`/`_is_test_file`/`_is_test_function`/
  `_qualify`/`NodeInfo`/`EdgeInfo`)
- **`diagrams/generate_diagrams.py`** (language groups never listed VB.NET),
  **`skills/`** (no VB.NET mentions), **`token_benchmark.py`**/**`agent_baseline.py`**
  (never contained `.vb`, re-verified)
- **`CHANGELOG.md`** (historical "bounded VB.NET structural parsing" entry),
  **`.serena/project.yml`** (no vbnet), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `vbnet`/`VB.NET`/`.vb`/
  `_vbnet_`/`_VBNET_` references remain in `code_review_graph/` and `tests/`
- 364 tests passed in `test_language_reconciliation.py` + `test_multilang.py` +
  `test_parser.py`
- Full suite: 1926 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `VB.NET` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.vb"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
