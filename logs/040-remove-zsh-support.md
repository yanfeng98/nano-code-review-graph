# 040 — Remove zsh Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed zsh support from the parser. zsh was not an independent language but a
bash variant: the `.zsh` extension mapping (`EXTENSION_TO_LANGUAGE`) and the
`#!/bin/zsh` shebang mapping (`SHEBANG_INTERPRETER_TO_LANGUAGE`) both routed to
`"bash"`. Removing them means `.zsh` files and `zsh` shebangs are no longer
recognized as source. The **bash language is unaffected**: `.sh`/`.bash`/`.ksh`
extensions and the `bash`/`sh`/`ksh`/`dash`/`ash` shebang keys still map to
bash, and `_builtin_language_names()` is unchanged (its value set still
contains `"bash"`).

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".zsh": "bash"` from `EXTENSION_TO_LANGUAGE`
  - Removed `"zsh": "bash"` from `SHEBANG_INTERPRETER_TO_LANGUAGE`
  - `.sh`/`.bash`/`.ksh` extensions and bash/sh/ksh/dash/ash shebangs retained

### Tests (1 file edited)
- **`tests/test_multilang.py`**: Removed the `run.zsh` detect_language
  assertion from `TestBashParsing.test_detects_language` (`.sh`/`.bash`/`.ksh`
  assertions retained)

### Documentation
- **`docs/USAGE.md`**: Removed `zsh` from the shebang interpreter list
  ("bash/sh/zsh/ksh/dash/ash" → "bash/sh/ksh/dash/ash")

### Not changed
- **`CHANGELOG.md`** (historical "Bash/Shell parser ... .sh, .bash, and .zsh
  files..." entry)
- **`docs/TROUBLESHOOTING.md`** (`~/.zshrc` macOS PATH instructions — unrelated
  to language mapping)
- **`tests/test_documentation.py`** (docstring "survive zsh globbing" — unrelated
  to language mapping)
- `README.md`/`docs/FEATURES.md`/`docs/LLM-OPTIMIZED-REFERENCE.md` (generic
  "shell scripts", no zsh mention), `skills/`, `diagrams/generate_diagrams.py`,
  `.serena/project.yml` (no zsh)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `zsh`/`Zsh`/`.zsh`
  references remain in `code_review_graph/` and `tests/`
- `detect_language(Path("x.zsh"))` → None; `detect_language(Path("x.sh"))`/
  `x.ksh` → `"bash"`; a `#!/bin/zsh` shebang script is no longer detected
- Full suite: 1721 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- bash retained: `TestBashParsing` (incl. the `.ksh` end-to-end test) passes
