# 038 — Remove Vue (vue) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Vue (`.vue`) language support from the parser and downstream consumers.
`.vue` files are no longer detected as source code. Vue is a single-file
component (SFC) whose `_parse_vue` method used the vue grammar to extract
`<script>` blocks, detect `lang="ts"`, delegate to the JS/TS parsers, and
offset line numbers back to `.vue` coordinates. Like Svelte (removed in
logs/032), Vue had **no entries** in the four node-type tables and no shebang
mapping. Unlike Svelte, Vue also appeared in shared JS/TS language tuples:
`_do_resolve_module` (`("javascript", "typescript", "tsx", "vue")` + the
`.vue` probe extension) and `_resolve_exported_symbol`
(`("javascript", "typescript", "tsx", "vue")`), plus the
`tsconfig_resolver._PROBE_EXTENSIONS` list. The `tree-sitter-vue` grammar
remains bundled inside `tree-sitter-language-pack` (a single wheel with ~170
grammars) and cannot be uninstalled independently, so the removal is at the
code/mapping layer only.

## Changes

### Core code (2 files)
- **`code_review_graph/parser.py`**:
  - Removed `".vue": "vue"` from `EXTENSION_TO_LANGUAGE`
  - Removed the `parse_bytes` Vue dispatch branch
  - Deleted the `_parse_vue` method (~111 lines)
  - Removed `"vue"` from `_do_resolve_module`'s JS/TS tuple and `".vue"` from
    its probe-extension list; removed `"vue"` from
    `_resolve_exported_symbol`'s guard tuple
  - `_builtin_language_names()` derives from the mappings — auto-excludes vue;
    shared helpers and `("javascript", "typescript", "tsx")` tuples untouched
- **`code_review_graph/tsconfig_resolver.py`**: Removed `".vue"` from
  `_PROBE_EXTENSIONS`; dropped `Vue` from the module docstring

### Tests (3 files edited + 1 fixture deleted)
- **`tests/test_multilang.py`**: Deleted `TestVueParsing` (7 test methods);
  removed `Vue` from module docstring
- **`tests/test_parser.py`**: Deleted the Vue SFC test section (9 test methods:
  detect language, parse file, imports, calls, contains, line-number offset,
  nodes language, empty script, js default)
- **`tests/test_tsconfig_resolver.py`**: `App.vue` importer → `App.js`
  (jsconfig alias-resolution test intent preserved)
- **`tests/fixtures/sample_vue.vue`**: Deleted

### Documentation
- **`README.md`**: Removed `Vue SFCs` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `Vue single-file components` from
  supported-languages list
- **`docs/FEATURES.md`**: Removed `Vue SFCs` from parser-surface list (kept
  historical "15 languages: Added Vue SFC and Solidity support" entry)
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Vue SFCs` from languages section
- **`skills/build-graph/SKILL.md`**: Removed `Vue` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Web group
  `["TypeScript", "JavaScript", "TSX", "Vue"]` → `["TypeScript", "JavaScript", "TSX"]`;
  regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (vue grammar bundled in wheel)
- Shared helpers and `("javascript", "typescript", "tsx")` tuples
- **`docs/ROADMAP.md`** (v1.8.4 historical entry), **`CHANGELOG.md`**
  (historical jsconfig + Vue SFC entries), **`.serena/project.yml`** (comment)
- `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `vue`/`Vue`/`.vue`/
  `_parse_vue` references remain in `code_review_graph/` and `tests/`
- 220 tests passed in `test_multilang.py` + `test_parser.py` +
  `test_tsconfig_resolver.py`
- Full suite: 1740 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Vue` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.vue"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- JS/TS shared tuples retained: `test_tsconfig_resolver.py` +
  `TestRustParsing`/`TestCParsing`/`TestVerilogParsing` pass
