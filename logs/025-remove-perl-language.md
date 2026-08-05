# 025 — Remove Perl (perl) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Perl (`.pl`/`.pm`/`.t`) language support from the parser and downstream
consumers, along with the `.xs` (Perl XS) extension mapping. `.pl`/`.pm`/`.t`
files are no longer detected as source code. Perl had no dedicated extraction
functions — it was driven entirely by four node-type table entries (classes
`package_statement`/`class_statement`/`role_statement`; functions
`subroutine_declaration_statement`/`method_declaration_statement`; imports
`use_statement`/`require_expression`; calls
`function_call_expression`/`method_call_expression`/
`ambiguous_function_call_expression`), two `if language == "perl"` branches
(`_get_name`, `_get_call_name`), one unguarded Perl-only fallback
(`_get_call_name` `first.type == "function"`), and one shebang mapping.
`.xs` (Perl XS) was mapped to the C grammar; per user decision it was removed
entirely rather than kept as a standalone C-parse feature. The
`tree-sitter-perl` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently,
so the removal is at the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".pl": "perl"`, `".pm": "perl"`, `".t": "perl"` from
    `EXTENSION_TO_LANGUAGE`
  - Removed `".xs": "c"` mapping (Perl XS) — **user decision: full removal**
  - Removed `"perl": "perl"` from `SHEBANG_INTERPRETER_TO_LANGUAGE`;
    `# Ruby / Perl / Lua` comment → `# Ruby / Lua`
  - Removed `"perl"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (all four entries non-empty; their node-type
    strings are Perl-only, not shared with any remaining language)
  - Removed `_get_name` Perl branch (bareword/package name extraction)
  - Removed `_get_call_name` Perl `method_call_expression` branch and the
    unguarded `first.type == "function"` fallback (tree-sitter-perl call nodes
    use a `function` child; no remaining language relies on it)
  - `_builtin_language_names()` derives from the mappings — auto-excludes perl;
    `_TYPED_CALL_LANGUAGES`/`block_types`/`parameter_types` had no perl entries;
    shared helpers (`_qualify`/`_resolve_call_target`/`_extract_calls`/
    `_get_params`/`_get_bases`/`_extract_import`) untouched

### Tests (2 files edited + 2 fixtures deleted)
- **`tests/test_multilang.py`**: Deleted `TestPerlParsing` (6 test methods:
  language detection, packages→classes, subroutines→functions, imports, calls
  including `method_call_expression`/`ambiguous_function_call_expression`,
  CONTAINS) and `TestXSParsing` (6 test methods: `.xs` detected as C, structs,
  functions, includes, calls, CONTAINS)
- **`tests/test_parser.py`**: Deleted `test_detect_shebang_perl`
  (`#!/usr/bin/env perl` shebang detection)
- **`tests/fixtures/sample.pl`**: Deleted
- **`tests/fixtures/sample.xs`**: Deleted (Perl XS fixture)

### Documentation
- **`README.md`**: Removed `Perl` and `Perl XS 文件（.xs）` from language
  lists (2 places)
- **`docs/USAGE.md`**: Removed `Perl` and `Perl XS files (.xs)` from
  supported-languages list; removed `Perl` from shebang interpreter list
- **`docs/FEATURES.md`**: Removed `Perl` and `Perl XS files` from parser-surface
  list (kept historical v2.0.0 "Added Dart, R, Perl support" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Perl` and `Perl XS files`
  from languages section
- **`CLAUDE.md`**: `test_multilang.py` description dropped "Perl XS"
- **`diagrams/generate_diagrams.py`**: Scripting domain group removed `Perl`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (perl grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings and remaining languages' node-type table entries
- **`CHANGELOG.md`** (historical "Perl XS support" entry), `docs/FEATURES.md`
  v2.0.0 historical entry, **`docs/ROADMAP.md`** v2.0.0 historical entry
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`
- C/C++ parsing (`.c`/`.h` unaffected by the `.xs` removal)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `perl`/`Perl`/`.pl`/
  `.pm`/`.t`/`.xs` references remain in `code_review_graph/` and `tests/`
- 387 tests passed in `test_multilang.py` + `test_parser.py`
- Full suite: 1962 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Perl` references in docs (except historical records)
- Diagram source regenerated
- End-to-end: `detect_language(Path("x.pl"))`/`x.xs` → None; Python/C still
  parse normally
- Self-audit verified the unguarded `first.type == "function"` fallback is
  Perl-only (no remaining grammar's call node starts with a `function` child)
