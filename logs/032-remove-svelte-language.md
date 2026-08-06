# 032 — Remove Svelte (svelte) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Svelte (`.svelte`) language support from the parser and downstream
consumers. `.svelte` files are no longer detected as source code. Svelte is a
single-file component (SFC) whose `_parse_svelte` method reused the vue grammar
to extract `<script>` blocks and delegate them to the JS/TS parsers. Svelte had
**no entries** in the four node-type tables, no shebang mapping, and no
module-level constants. `_parse_svelte` was an independent copy of `_parse_vue`
(they never call each other; the only coupling is svelte→vue grammar fallback,
a one-way dependency), so **Vue is unaffected**. There were **no tests** for
Svelte (no `TestSvelteParsing`, no `.svelte` fixture, no test references), so
no tests/fixtures needed removal. The `tree-sitter-svelte`/`tree-sitter-vue`
grammars remain bundled inside `tree-sitter-language-pack` (a single wheel with
~170 grammars) and cannot be uninstalled independently, so the removal is at
the code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".svelte": "svelte"` from `EXTENSION_TO_LANGUAGE`
  - Removed the `parse_bytes` Svelte dispatch branch
    (`if language == "svelte": return self._parse_svelte(...)`) and its comment
  - Deleted the `_parse_svelte` method (~130 lines): vue-grammar fallback,
    `<script>` block extraction, JS/TS delegation, File node
    (`language="svelte"`), TESTED_BY edges
  - `_builtin_language_names()` derives from the mappings — auto-excludes
    svelte; `_parse_vue` and all shared helpers (`_get_parser`/
    `normalize_file_path`/`_is_test_file`/`_collect_file_scope`/
    `_extract_from_tree`/`_qualify`) untouched

### Tests
- **None** — `tests/` had zero Svelte references (no test class, no fixture,
  no assertions). `TestVueParsing` and the Vue SFC tests in `test_parser.py`
  are retained (Vue unaffected)

### Documentation
- **`README.md`**: `Vue/Svelte SFCs` → `Vue SFCs` (2 places)
- **`docs/USAGE.md`**: `Vue/Svelte single-file components` → `Vue single-file components`
- **`docs/FEATURES.md`**: `Vue/Svelte SFCs` → `Vue SFCs`
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: `Vue/Svelte SFCs` → `Vue SFCs`
- **`diagrams/generate_diagrams.py`**: Web group
  `["TypeScript", "JavaScript", "TSX", "Vue", "Svelte"]` → removed `Svelte`;
  regenerated `.excalidraw` sources

### Not changed
- **Vue parsing** (`_parse_vue`, Vue SFC tests, `sample_vue.vue` fixture)
- **`tree-sitter-language-pack`** dependency (svelte/vue grammars bundled)
- **`token_benchmark.py`**/**`agent_baseline.py`** (no `.svelte`, re-verified)
- **`CHANGELOG.md`** (historical "4 new languages: ... Svelte SFC" entry),
  `.serena/project.yml` (no svelte), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `svelte`/`Svelte`/
  `.svelte` references remain in `code_review_graph/` and `tests/`
- Full suite: 1869 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Svelte` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.svelte"))` → None;
  `detect_language(Path("x.py"))`/`x.vue` still work
- **Vue retained**: `TestVueParsing` + Vue SFC tests in `test_parser.py` pass
