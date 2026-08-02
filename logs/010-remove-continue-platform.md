# 010 — Remove Continue Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Continue platform integration. Continue was minimal — PLATFORMS entry with `"format": "array"` (the only array-format platform), no hooks, no skills, no instruction files. Test fixtures using `.continue/config.json` (from Qoder removal) were updated to use `.codex/config.toml` and `.opencode.json`.

## Changes

### Core code (2 files, 11 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["continue"]` entry (the only array-format platform)
- **`code_review_graph/cli.py`**:
  - Removed `"continue"` from `_PLATFORM_CHOICES`

### Tests (2 files, 91 lines removed)
- **`tests/test_skills.py`**:
  - Deleted `test_install_continue_config`
  - Deleted `test_continue_array_no_duplicate`
  - Removed `_run_continue` helper and `test_array_platform_preserves_wrong_typed_server_collection`
  - Removed entire `TestInstallConfigDataLoss` class (Zed tests were already removed earlier)
  - Removed continue override from `test_install_all_detected`
- **`tests/test_uninstall.py`**:
  - Changed malformed config path: `.continue/config.json` → `.opencode.json`
  - Changed user config path: `.continue/config.json` → `.codex/config.toml`

### Documentation (9 files)
- **`README.md`**: Removed Continue from platform list (3 places)
- **`README.zh-CN.md`**: Removed Continue from platform list
- **`README.ja-JP.md`**: Removed Continue from platform list
- **`README.ko-KR.md`**: Removed Continue from platform list
- **`README.hi-IN.md`**: Removed Continue from platform list
- **`CLAUDE.md`**: Removed Continue from project overview
- **`docs/USAGE.md`**: Removed Continue row
- **`docs/architecture.md`**: Removed Continue from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Continue row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Continue from supported list

## Verification
- 145 tests passed
- Ruff lint: all checks passed
- Zero `continue` platform references in Python files (only `parser.py` keyword list)
