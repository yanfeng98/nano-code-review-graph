# 003 — Remove Cursor Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Cursor platform integration code and documentation references. Cursor was the most deeply integrated platform removed so far — it had dedicated hooks (`generate_cursor_hooks_config`, `_cursor_hook_scripts`, `install_cursor_hooks`), instruction files (`.cursorrules` + `AGENTS.md` as co-owner), MCP config, and uninstall cleanup.

Key constraint: AGENTS.md is shared by multiple platforms (opencode, antigravity, codex) and must continue to work for them. `.cursorrules` was Cursor-only and removed entirely.

## Changes

### Core code (3 files, 235 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["cursor"]` dictionary entry
  - Updated `_PLATFORM_INSTRUCTION_FILES`: removed `".cursorrules": ("cursor",)`, changed AGENTS.md owners from `("cursor", "opencode", "antigravity", "codex")` to `("opencode", "antigravity", "codex")`
  - Updated module docstring: "Cursor hooks / OpenCode plugin generation" → "OpenCode plugin generation"
  - Updated `inject_platform_instructions` docstring to remove cursor references
  - Removed `generate_cursor_hooks_config()` function
  - Removed `_cursor_hook_scripts()` function
  - Removed `install_cursor_hooks()` function
  - Removed unused `import stat`
- **`code_review_graph/cli.py`**:
  - Removed `"cursor"` from `_PLATFORM_CHOICES`
  - Removed `install_cursor_hooks` import
  - Removed Cursor hooks install block (6 lines)
- **`code_review_graph/uninstall.py`**:
  - Removed Cursor hooks cleanup block (references to `generate_cursor_hooks_config()` and `_cursor_hook_scripts()`)

### Tests (3 files, 309 lines removed)
- **`tests/test_skills.py`**:
  - Removed imports: `_cursor_hook_scripts`, `generate_cursor_hooks_config`, `install_cursor_hooks`
  - Deleted `TestCursorHooksConfig` class (6 methods)
  - Deleted `TestCursorHookScripts` class (7 methods)
  - Deleted `TestInstallCursorHooks` class (6 methods)
  - Deleted `test_install_cursor_config`
  - Deleted `test_cursor_writes_only_cursor_files`
  - Deleted `test_install_cursor_hooks_preserves_non_ascii_field`
  - Removed `".cursorrules"` from expected sets/assertions in 6 tests
  - Removed cursor override from `test_install_all_detected`
- **`tests/test_uninstall.py`**:
  - Deleted `test_cursor_shared_hooks_directory_keeps_unrelated_scripts`
  - Deleted `test_hook_cleanup_handles_owned_entries_and_mixed_nested_groups`
  - Changed malformed config test path from `.cursor/mcp.json` to `.kiro/settings/mcp.json`
- **`tests/test_cli_install.py`**:
  - Deleted `test_handle_init_cursor_installs_cursor_hooks`

### Documentation (10 files)
- **`README.md`**: Removed Cursor from platform list (3 places)
- **`README.zh-CN.md`**: Removed Cursor from platform list
- **`README.ja-JP.md`**: Removed Cursor from platform list
- **`README.ko-KR.md`**: Removed Cursor from platform list
- **`README.hi-IN.md`**: Removed Cursor from platform list
- **`CLAUDE.md`**: Removed Cursor from project overview
- **`docs/USAGE.md`**: Removed Cursor row from platform config table
- **`docs/architecture.md`**: Removed Cursor from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Cursor row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Cursor from supported list

## Preserved
- AGENTS.md still generated for opencode, antigravity, codex
- OpenCode legacy `.cursor/mcp.json` uninstall handler kept (OpenCode compatibility, not Cursor)
- JSON parser incidental `cursor` variable names untouched
- CSS `cursor: pointer` references untouched

## Verification
- 205 tests passed
- Ruff lint: all checks passed
- Zero `install_cursor_hooks`/`generate_cursor_hooks_config`/`_cursor_hook_scripts` references in Python files
