# 041 — Remove .ksh Support

**Date:** 2026-08-05
**Branch:** 260802-v2.3.7

## Summary

Removed .ksh (Korn shell) support from the parser. Like zsh (logs/040), ksh was
not an independent language but a bash variant: the `.ksh` extension mapping
(`EXTENSION_TO_LANGUAGE`) and the `#!/bin/ksh` shebang mapping
(`SHEBANG_INTERPRETER_TO_LANGUAGE`) both routed to `"bash"`. Removing them means
`.ksh` files and `ksh` shebangs are no longer recognized as source. The **bash
language is unaffected**: `.sh`/`.bash` extensions and the `bash`/`sh`/`dash`/
`ash` shebang keys still map to bash, and `_builtin_language_names()` is
unchanged (its value set still contains `"bash"`).

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".ksh": "bash"` (with the `#235` comment) from
    `EXTENSION_TO_LANGUAGE`
  - Removed `"ksh": "bash"` from `SHEBANG_INTERPRETER_TO_LANGUAGE`
  - `.sh`/`.bash` extensions and bash/sh/dash/ash shebangs retained

### Tests (1 file edited)
- **`tests/test_multilang.py`**: Removed the `legacy.ksh` detect_language
  assertion and the `test_ksh_extension_parses_as_bash` end-to-end method (a
  real `.ksh` fixture parsed via the bash grammar, compared against `.sh`) from
  `TestBashParsing` (`.sh`/`.bash` assertions retained)

### Documentation
- **`docs/USAGE.md`**: Removed `ksh` from the shebang interpreter list
  ("bash/sh/ksh/dash/ash" → "bash/sh/dash/ash")

### Not changed
- **`CHANGELOG.md`** (historical .ksh shebang-detection entry, and the
  "Bash/Shell parser" entry)
- **`docs/TROUBLESHOOTING.md`** (`~/.zshrc` macOS PATH instructions — unrelated),
  **`tests/test_documentation.py`** (docstring — unrelated)
- `README.md`/`docs/FEATURES.md`/`docs/LLM-OPTIMIZED-REFERENCE.md` (generic
  "shell scripts", no ksh mention), `skills/`, `diagrams/generate_diagrams.py`,
  `.serena/project.yml` (no ksh)

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `ksh`/`Ksh`/`.ksh`
  references remain in `code_review_graph/` and `tests/`
- `detect_language(Path("x.ksh"))` → None; `detect_language(Path("x.sh"))`/
  `x.bash` → `"bash"`; a `#!/bin/ksh` shebang script is no longer detected
- Full suite: 1720 passed, 5 skipped (2 pre-existing `test_documentation.py`
  failures from a missing `README.hi-IN.md`, unrelated)
- bash retained: `TestBashParsing` passes
