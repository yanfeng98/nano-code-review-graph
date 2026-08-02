# 008 — Remove Zed Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Zed platform integration code. Zed was simple — PLATFORMS entry, a `_zed_settings_path()` helper for OS-specific path resolution, and MCP config with `context_servers` key. Also removed the unused `import platform` from skills.py (Zed was the last consumer of `platform.system()`).

## Changes

### Core code (2 files)
- **`code_review_graph/skills.py`**:
  - Removed `_zed_settings_path()` function
  - Removed `PLATFORMS["zed"]` entry
  - Removed unused `import platform`
- **`code_review_graph/cli.py`**:
  - Removed `"zed"` from `_PLATFORM_CHOICES`

### Tests (2 files)
- **`tests/test_skills.py`**:
  - Deleted `test_install_zed_config`
  - Removed zed override from `test_install_all_detected`
  - Removed `_run_zed` helper and 5 zed-specific tests from `TestInstallConfigDataLoss` (kept 2 Continue tests)
- **`tests/test_uninstall.py`**:
  - Changed parametrize from `["zed", "opencode"]` to `["opencode"]`

### Documentation (9 files)
- **`README.md`**: Removed Zed from platform list (3 places)
- **`README.zh-CN.md`**: Removed Zed from platform list
- **`README.ja-JP.md`**: Removed Zed from platform list
- **`README.ko-KR.md`**: Removed Zed from platform list
- **`README.hi-IN.md`**: Removed Zed from platform list
- **`CLAUDE.md`**: Removed Zed from project overview
- **`docs/USAGE.md`**: Removed Zed row
- **`docs/architecture.md`**: Removed Zed from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Zed row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Zed from supported list

## Verification
- 152 tests passed
- Ruff lint: all checks passed
- Zero `zed` platform references in Python files
