# 007 — Remove GitHub Copilot + Copilot CLI Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed both "copilot" (GitHub Copilot VS Code) and "copilot-cli" (GitHub Copilot CLI) platform integrations. This was the most complex removal — Copilot had a dedicated detection function spanning 3 OSes, a custom instruction file format with YAML front matter, legacy migration support, legacy MCP config keys, and 26 test methods.

## Changes

### Core code (2 files, 205 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `_copilot_vscode_detected()` function (~80 lines covering macOS/Windows/Linux VS Code detection)
  - Removed `PLATFORMS["copilot"]` and `PLATFORMS["copilot-cli"]` entries
  - Removed `_COPILOT_SECTION` constant (~50 lines of YAML+markdown instruction content)
  - Removed `_PLATFORM_INSTRUCTION_CUSTOM_SECTIONS` (both entries were copilot-only, kept empty dict)
  - Removed `".github/instructions/code-review-graph.instructions.md"` from `_PLATFORM_INSTRUCTION_FILES`
  - Removed `_LEGACY_PLATFORM_INSTRUCTION_FILES` entries (kept empty dict for uninstall compat)
  - Removed `_remove_legacy_instruction_file()` function
  - Removed legacy cleanup loop from `inject_platform_instructions()`
- **`code_review_graph/cli.py`**:
  - Removed `"copilot"` and `"copilot-cli"` from `_PLATFORM_CHOICES`

### Tests (3 files, 496 lines removed)
- **`tests/test_skills.py`**:
  - Removed `_copilot_vscode_detected` import
  - Deleted `TestCopilotPlatform` class (11 methods)
  - Deleted `TestCopilotCLIPlatform` class (9 methods)
  - Removed `.github/instructions/code-review-graph.instructions.md` from expected sets
- **`tests/test_cli_install.py`**:
  - Deleted `test_copilot_cli_install_reinstall_uninstall_lifecycle` (~75 lines)
  - Removed unused `skills, uninstall` import
- **`tests/test_uninstall.py`**:
  - Deleted `test_copilot_cli_uninstall_removes_current_and_legacy_entries`
  - Deleted `test_uninstall_cleans_current_and_legacy_copilot_instruction_paths`

### Documentation (10 files)
- **`README.md`**: Removed Copilot from platform list (3 places)
- **`README.zh-CN.md`**: Removed Copilot from platform list
- **`README.ja-JP.md`**: Removed Copilot from platform list
- **`README.ko-KR.md`**: Removed Copilot from platform list
- **`README.hi-IN.md`**: Removed Copilot from platform list
- **`CLAUDE.md`**: Removed Copilot from project overview
- **`docs/USAGE.md`**: Removed both Copilot rows
- **`diagrams/generate_diagrams.py`**: Removed both Copilot rows
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Copilot from supported list

## Verification
- 162 tests passed
- Ruff lint: all checks passed
- Zero `copilot` references in Python files
