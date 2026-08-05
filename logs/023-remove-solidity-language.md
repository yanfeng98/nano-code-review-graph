# 023 — Remove Solidity (solidity) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Solidity (`.sol`) language support from the parser and downstream
consumers. `.sol` files are no longer detected as source code. Solidity had
one dedicated function (`_extract_solidity_constructs` handling
emit/state-variable/constant/using-directive constructs) and eight condition
branches across `_extract_from_tree`, `_extract_calls` (modifier invocations),
`_get_name`, `_get_params`, `_get_bases`, `_extract_import`, and
`_get_call_name`. The `tree-sitter-solidity` grammar remains bundled inside
`tree-sitter-language-pack` (a single wheel with ~170 grammars) and cannot be
uninstalled independently, so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".sol": "solidity"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"solidity"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared node-type strings like
    `interface_declaration`/`struct_declaration`/`function_definition`/
    `call_expression` preserved for TS/Verilog/C/etc.; solidity-only
    `contract_declaration`/`library_declaration`/`error_declaration`/
    `user_defined_type_definition`/`constructor_definition`/
    `modifier_definition`/`event_definition`/`fallback_receive_definition`/
    `import_directive` removed)
  - Deleted `_extract_solidity_constructs` (emit statements, state/constant
    variable declarations, using directives)
  - Removed 8 condition branches: `_extract_from_tree` dispatch,
    `_extract_calls` modifier invocations, `_get_name` constructor/receive/
    fallback, `_get_params` Solidity parameters, `_get_bases` inheritance
    specifier, `_extract_import` import directive, `_get_call_name` expression
    unwrap
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no solidity entries — untouched

### Tests (1 file edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestSolidityParsing` class
  (~27 test methods); removed `Solidity` from module docstring
- **`tests/fixtures/sample.sol`**: Deleted

### Documentation
- **`README.md`**: Removed `Solidity` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Solidity` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Solidity` from parser-surface list (kept
  historical v1.x "Added Vue SFC and Solidity support" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Solidity` from languages
  section
- **`skills/build-graph/SKILL.md`**: Removed `Solidity` from supported-languages
  list
- **`diagrams/generate_diagrams.py`**: Domain group removed `Solidity`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (solidity grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings (`interface_declaration`/`struct_declaration`/
  `function_definition`/`call_expression`)
- **`CHANGELOG.md`**, `docs/FEATURES.md` v1.x historical entry, other
  historical records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `solidity`/`Solidity`/
  `.sol` references remain in `code_review_graph/`
- 257 tests passed in `test_multilang.py`
- Zero `Solidity` references in docs (except historical records)
- Diagram source regenerated
