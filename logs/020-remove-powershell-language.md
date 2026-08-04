# 020 — Remove PowerShell (powershell) Language Support

**Date:** 2026-08-04
**Branch:** 260802-v2.3.7

## Summary

Removed PowerShell (`.ps1`/`.psm1`/`.psd1`) language support from the parser
and downstream consumers. `.ps1`/`.psm1`/`.psd1` files are no longer detected
as source code. PowerShell was the simplest language removed so far: it had
**no condition branches, no dedicated functions, no constants, no comments,
and no test coverage** — only seven data entries in the parser (three extension
mappings and four node-type-table keys). The `tree-sitter-powershell` grammar
remains bundled inside `tree-sitter-language-pack` (a single wheel with ~170
grammars) and cannot be uninstalled independently, so the removal is at the
code/mapping layer only.

## Changes

### Core code (1 file)
- **`code_review_graph/parser.py`**:
  - Removed `".ps1": "powershell"`, `".psm1": "powershell"`,
    `".psd1": "powershell"` from `EXTENSION_TO_LANGUAGE`
  - Removed the `"powershell"` keys from `_CLASS_TYPES`, `_FUNCTION_TYPES`,
    `_IMPORT_TYPES`, `_CALL_TYPES` (shared `class_statement` preserved for
    Perl; `function_statement`/`command_expression` were PowerShell-only)
  - `_TYPED_CALL_LANGUAGES`, `block_types`, `parameter_types`, and
    `_builtin_language_names()` had no powershell entries — untouched

### Tests
- **No PowerShell tests or fixtures existed** — nothing to delete

### Documentation
- **`README.md`**: Removed `PowerShell` from language lists (2 places)
- **`docs/USAGE.md`**: Removed `PowerShell` from supported-languages list
- **`docs/FEATURES.md`**: Removed `PowerShell` from parser-surface list
- **`docs/LLM-OPTIMIZED-REFERENCE.md`**: Removed `PowerShell` from languages
  section
- **`diagrams/generate_diagrams.py`**: Shells group `["Bash", "PowerShell"]`
  → `["Bash"]`; regenerated `.excalidraw` sources

### Not changed
- **`tree-sitter-language-pack`** dependency (powershell grammar bundled in
  wheel, cannot be uninstalled separately)
- **`class_statement`** node-type string (Perl uses it)
- **`CHANGELOG.md`**, `docs/MAINTAINER_RECONCILIATION_2026-07-17.md`, historical
  records
- **`.serena/project.yml`** (comment-only language list), `code-review-graph-vscode/`

## Verification
- `code_review_graph/parser.py` imports cleanly; zero `powershell`/`PowerShell`/
  `.ps1`/`.psm1`/`.psd1` references remain in `code_review_graph/`
- Zero `PowerShell` references in docs (except historical records)
- Diagram source regenerated
