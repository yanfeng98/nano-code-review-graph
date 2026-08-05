# 026 — Remove Ruby (ruby) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Ruby (`.rb`) language support from the parser and downstream
consumers. `.rb` files are no longer detected as source code. Ruby had no
dedicated extraction functions — it was driven entirely by four node-type
table entries (`"class"`/`"module"` for classes, `"method"`/
`"singleton_method"` for functions, `"call"` for imports,
`"call"`/`"method_call"` for calls), two `if language == "ruby"` branches
(`_extract_import` require/require_relative, `_get_call_name` `method` field
extraction), and one shebang mapping. The `"class"` node type is shared with
JavaScript/TypeScript/TSX and `"call"` with Python — both remain registered
for those languages; `"module"`/`"method"`/`"singleton_method"`/
`"method_call"` were Ruby-only. The `tree-sitter-ruby` grammar remains bundled
inside `tree-sitter-language-pack` (a single wheel with ~170 grammars) and
cannot be uninstalled independently, so the removal is at the code/mapping
layer only.

## Changes

### Core code (4 files)
- **`code_review_graph/parser.py`**:
  - Removed `".rb": "ruby"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"ruby": "ruby"` from `SHEBANG_INTERPRETER_TO_LANGUAGE`;
    `# Ruby / Lua` comment → `# Lua`
  - Removed `"ruby"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared strings `"class"`/`"call"` remain
    registered for JS/TS/TSX and Python respectively)
  - Removed `_extract_import` Ruby branch (require/require_relative regex
    extraction)
  - Removed `_get_call_name` Ruby branch (`call`/`method_call` `method` field
    extraction)
  - Updated two comments that used Ruby as an example of a node type shared
    between imports and calls (`_extract_from_tree` fall-through comment and
    `_extract_imports` docstring incl. "See: Ruby call graph") to generic
    wording; the fall-through mechanism stays for custom languages
  - `_builtin_language_names()` derives from the mappings — auto-excludes ruby;
    `_TYPED_CALL_LANGUAGES`/`block_types`/`parameter_types` had no ruby entries;
    shared helpers (`_extract_from_tree`/`_extract_classes`/`_extract_functions`/
    `_get_name`/`_get_params`/`_get_bases`/`_qualify`) untouched

### Core code (benchmark/token paths)
- **`code_review_graph/token_benchmark.py`**: Removed `".rb"` from the token
  estimate source-extension tuple (`.rb` files are no longer parseable)
- **`code_review_graph/eval/benchmarks/agent_baseline.py`**: Removed `".rb"`
  from `_SOURCE_EXTS` (eval baseline source-extension tuple)
- **`code_review_graph/incremental.py`**: `DEFAULT_IGNORE_PATTERNS`
  `"**/.bundle/**"` kept but `# Ruby / Bundler` comment → `# Bundler` — the
  pattern is a generic framework-ignore default (PR #222), not a Ruby parsing
  dependency; the pattern itself stays

### Tests (2 files edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestRubyParsing` (5 methods:
  language detection, classes, methods, calls); removed `Ruby` from module
  docstring
- **`tests/test_parser.py`**: Deleted `test_detect_shebang_ruby`
  (`#!/usr/bin/env ruby` shebang detection)
- **`tests/fixtures/sample.rb`**: Deleted (sole `.rb` fixture)

### Documentation
- **`README.md`**: Removed `Ruby` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Ruby` from supported-languages list; removed
  `Ruby` from shebang interpreter list
- **`docs/FEATURES.md`**: Removed `Ruby` from parser-surface list (kept
  historical v1.6.2 "name extraction ... Ruby (constant)" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Ruby` from languages section
- **`docs/GITHUB_ACTION.md`**: Removed `Ruby` from lockfile-hash description
- **`skills/build-graph/SKILL.md`**: Removed `Ruby` from supported-languages
  list
- **`diagrams/generate_diagrams.py`**: Scripting domain group removed `Ruby`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (ruby grammar bundled in wheel,
  cannot be uninstalled separately)
- Shared node-type strings (`class`/`call`) registered for other languages
- **`CHANGELOG.md`** (historical entries: `.bundle/**` ignore default,
  name-extraction fix, fixture list), `docs/FEATURES.md` v1.6.2 historical
  entry
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`
- `DEFAULT_IGNORE_PATTERNS` (see above)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `ruby`/`Ruby`/`.rb`
  references remain in `code_review_graph/` and `tests/`
- 382 tests passed in `test_multilang.py` + `test_parser.py`
- Full suite: 1957 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Ruby` references in docs (except historical records)
- Diagram source regenerated
- End-to-end: `detect_language(Path("x.rb"))` → None; Python/JS still parse
  normally (shared `class`/`call` strings unaffected)
