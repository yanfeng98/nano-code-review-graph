# 009 — Remove Qoder Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Qoder platform integration including PLATFORMS entry, hooks support, `install_qoder_skills()` function, instruction file `QODER.md`, uninstall cleanup, tests, and documentation references.

## Changes

### Core code (3 files, 87 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["qoder"]` entry
  - Removed `"QODER.md"` from `_PLATFORM_INSTRUCTION_FILES`
  - Removed `install_qoder_skills()` function (~38 lines)
  - Simplified `install_hooks()`: removed qoder branch, now just claude
- **`code_review_graph/cli.py`**:
  - Removed `"qoder"` from `_PLATFORM_CHOICES`
  - Removed `install_qoder_skills` import
  - Removed Qoder skills install block
  - Updated hooks target: `("claude", "qoder", "all")` → `("claude", "all")`, `["claude", "qoder"]` → `["claude"]`
- **`code_review_graph/uninstall.py`**:
  - Removed Qoder hooks cleanup
  - Removed Qoder skills copy cleanup (source_skills block)

### Tests (2 files, 68 lines removed)
- **`tests/test_skills.py`**:
  - Deleted `test_install_qoder_hooks`, `test_install_qoder_hooks_merges_existing`
  - Deleted `test_install_qoder_config`
  - Deleted `test_qoder_writes_only_qoder_md`
  - Removed `"QODER.md"` from all instruction file assertions
- **`tests/test_uninstall.py`**:
  - Removed qoder skill assertions from skills directory test
  - Changed malformed config path: `.qoder/mcp.json` → `.continue/config.json` (with home-relative path fix)
  - Changed user config path: `.qoder/mcp.json` → `.continue/config.json`

### Documentation (9 files)
- **`README.md`**: Removed Qoder from platform list (3 places)
- **`README.zh-CN.md`**: Removed Qoder from platform list
- **`README.ja-JP.md`**: Removed Qoder from platform list
- **`README.ko-KR.md`**: Removed Qoder from platform list
- **`README.hi-IN.md`**: Removed Qoder from platform list
- **`CLAUDE.md`**: Removed Qoder from project overview
- **`docs/USAGE.md`**: Removed Qoder row
- **`docs/architecture.md`**: Removed Qoder from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Qoder row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Qoder from supported list

## Verification
- 149 tests passed (147 + 2 cli)
- Ruff lint: all checks passed
- Zero `qoder` references in Python files
