# 035 — Remove Go (go) Language Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed Go (`.go`) language support from the parser and downstream consumers.
`.go` files are no longer detected as source code. Go is a first-class
tree-sitter language with four non-empty node-type table entries
(`type_declaration`/`function_declaration`+`method_declaration`/
`import_declaration`/`call_expression`), one dedicated helper
`_get_go_receiver_type` (method-receiver extraction, sole caller in
`_extract_functions`), and 7 `if language == "go"` branches embedded in shared
methods (`_line_doc_payload`/`_preceding_doc_comment`/`_extract_functions`/
`_get_name`×2/`_get_bases`/`_extract_import`), plus the `.*_test\.go$`
test-file pattern. Shared node-type strings (`function_declaration`/
`call_expression`/`type_declaration`) remain for other languages;
`method_declaration`/`import_declaration` were Go-only. The dead-guard walk
(`_is_in_static_dead_guard`) is language-independent and retained.

**User decisions:**
- **Go eval config deleted** — `code_review_graph/eval/configs/gin.yaml`
  (Go web framework) + `evaluate/results/gin_*.csv` (3 result data files)
- **dead-guard tests replaced with TypeScript** — the Go fragments in
  `TestDeadGuardHelpers` and the Go dead-guard fixture tests were switched to
  TS (TS variants already existed in the same test class)

The `tree-sitter-go` grammar remains bundled inside `tree-sitter-language-pack`
(a single wheel with ~170 grammars) and cannot be uninstalled independently, so
the removal is at the code/mapping layer only.

## Changes

### Core code (4 files + eval assets)
- **`code_review_graph/parser.py`**:
  - Removed `".go": "go"` from `EXTENSION_TO_LANGUAGE` and
    `.*_test\.go$` from `_TEST_FILE_PATTERNS`
  - Removed the four `"go"` node-type table entries
  - Deleted the 7 `if language == "go"` branches in shared methods and
    `_get_go_receiver_type`
  - Updated dead-guard docstrings/comments that referenced Go (logic retained)
  - `_builtin_language_names()` derives from the mappings — auto-excludes go;
    shared helpers and js/ts/tsx/verilog/c/cpp/rust strings untouched
- **`code_review_graph/token_benchmark.py`**: Dropped `".go"` from the token
  estimate source-extension tuple
- **`code_review_graph/eval/benchmarks/agent_baseline.py`**: Dropped `".go"`
  from `_SOURCE_EXTS`
- **`code_review_graph/eval/configs/gin.yaml`**: Deleted (user decision)
- **`evaluate/results/gin_*.csv`** (3 files): Deleted (user decision)

### Tests (5 files edited + 2 fixtures deleted)
- **`tests/test_multilang.py`**: Deleted `TestGoParsing` (8 test methods);
  removed `Go` from module docstring
- **`tests/test_parser.py`**: Deleted `test_go_dead_guard_if_false_omits_dead_edges`
  (TS variant exists), `test_extract_calls_skips_dead_go` (TS variant exists),
  the Go case in `test_dead_guard_calls_absent_from_graph_store`, and replaced
  the 11 `_parse("go", ...)` dead-guard fragments with TypeScript
  (`_parse("typescript", ...)` + TS code + `block`→`statement_block`)
- **`tests/test_docstring_embeddings.py`**: Go docstring tests replaced with a
  TypeScript `///` variant; the Go-only `go:` compiler-directive test deleted
- **`tests/test_parser_load_probe.py`**: `_parser_load_probe_succeeds("go")` →
  `"zig"`
- **`tests/test_notebook.py`**: `go` kernel metadata → `bash`
  (non-python-kernel test intent preserved)
- **`tests/test_incremental.py`**: `c.go` filename sample → `c.rs`
- **`tests/fixtures/sample_go.go`**: Deleted
- **`tests/fixtures/sample_dead_guard.go`**: Deleted (dead-guard tests now use
  TS/C fixtures)

### Documentation
- **`README.md`**: Removed `Go` from language lists and the flow-detection
  limitation (2+ places)
- **`docs/USAGE.md`**: Removed `Go` from supported-languages list
- **`docs/FEATURES.md`**: Removed `Go` from parser-surface and verified list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `Go` from languages section
- **`docs/FAQ.md`**: "Flow detection on JS/Go" → JS
- **`docs/schema.md`**: Removed `go` from language example and test-pattern/IMPLEMENTS mentions
- **`docs/REPRODUCING.md`**: Removed `Go`/gin from calibration descriptions
- **`docs/GITHUB_ACTION.md`**: "Python/JS/Go/Rust lockfiles"/`go.sum` → dropped Go
- **`skills/build-graph/SKILL.md`**: Removed `Go` from supported-languages list
- **`diagrams/generate_diagrams.py`**: Removed the `gin` benchmark card and `Go`
  from the Backend group; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (go grammar bundled in wheel)
- Shared node-type strings and shared helpers
- **`CHANGELOG.md`** (historical Go entries incl. method-receiver support),
  **`.serena/project.yml`** (comment tokens, kept by convention)
- `code-review-graph-vscode/` and "Google"/"Godot"/Rust `fn go()` false positives

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `go`/`Go`/`.go`/
  `_get_go_receiver_type` references remain in `code_review_graph/` and `tests/`
- 427 tests passed across `test_multilang.py` + `test_parser.py` +
  `test_notebook.py` + `test_incremental.py` + `test_docstring_embeddings.py` +
  `test_parser_load_probe.py` + `test_windows_path_identity.py`
- Full suite: 1774 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- Zero `Go` references in docs (except historical records)
- End-to-end: `detect_language(Path("x.go"))` → None;
  `detect_language(Path("x.py"))`/`x.js` still work
- js/ts/tsx/verilog/c/cpp/rust shared strings retained:
  `TestRustParsing`/`TestCParsing`/`TestCppParsing`/`TestVerilogParsing` pass
