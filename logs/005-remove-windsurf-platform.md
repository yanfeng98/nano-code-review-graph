# 005 — Remove Windsurf Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Windsurf platform integration code. Windsurf was simple — PLATFORMS entry, instruction file (`.windsurfrules`), MCP config. No dedicated hooks or uninstall code.

Also removed stale `cursor` and `windsurf` entries from the bug report issue template dropdown that were missed in earlier removals.

## Changes

### Core code (2 files)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["windsurf"]` entry
  - Removed `".windsurfrules": ("windsurf",)` from `_PLATFORM_INSTRUCTION_FILES`
  - Updated `inject_platform_instructions` docstring
- **`code_review_graph/cli.py`**:
  - Removed `"windsurf"` from `_PLATFORM_CHOICES`

### Tests (1 file)
- **`tests/test_skills.py`**:
  - Deleted `test_windsurf_writes_only_windsurfrules`
  - Deleted `test_install_windsurf_config`
  - Deleted `test_windsurf_install_does_not_create_claude_skills`
  - Also deleted `test_cursor_install_does_not_create_claude_skills` (missed in 003)
  - Removed `.windsurfrules` from 6 test assertions
  - Removed windsurf override from `test_install_all_detected`

### Documentation (12 files)
- **`README.md`**: Removed Windsurf from platform list (3 places)
- **`README.zh-CN.md`**: Removed Windsurf from platform list
- **`README.ja-JP.md`**: Removed Windsurf from platform list
- **`README.ko-KR.md`**: Removed Windsurf from platform list
- **`README.hi-IN.md`**: Removed Windsurf from platform list
- **`CLAUDE.md`**: Removed Windsurf from project overview
- **`docs/USAGE.md`**: Removed Windsurf row
- **`docs/architecture.md`**: Removed Windsurf from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Windsurf row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Windsurf from supported list
- **`.github/ISSUE_TEMPLATE/bug_report.yml`**: Removed Windsurf + cursor from AI platform dropdown

## Verification
- 149 tests passed
- Ruff lint: all checks passed
- Zero `windsurf`/`windsurfrules`/`codeium` references in Python files
