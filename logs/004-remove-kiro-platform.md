# 004 — Remove Kiro Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Kiro platform integration code. Kiro was the simplest platform removed so far — no dedicated hooks or skills functions, just a PLATFORMS entry, workspace-level detection logic, an instruction file (`.kiro/steering/code-review-graph.md`), and MCP config.

Note: two test fixtures in `test_uninstall.py` that previously used `.kiro/` paths (from earlier platform removals) were updated to use `.qoder/` paths instead.

## Changes

### Core code (2 files, 15 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["kiro"]` dictionary entry
  - Removed workspace-level Kiro detection block in `install_platform_configs`
  - Removed `".kiro/steering/code-review-graph.md": ("kiro",)` from `_PLATFORM_INSTRUCTION_FILES`
- **`code_review_graph/cli.py`**:
  - Removed `"kiro"` from `_PLATFORM_CHOICES`

### Tests (2 files, 101 lines removed)
- **`tests/test_skills.py`**:
  - Deleted `TestKiroPlatform` class (9 methods)
  - Removed `.kiro/steering/code-review-graph.md` from expected sets in 2 tests
- **`tests/test_uninstall.py`**:
  - Changed malformed config test path: `.kiro/settings/mcp.json` → `.qoder/mcp.json`
  - Changed user config test path: `.kiro/settings/mcp.json` → `.qoder/mcp.json`

### Documentation (10 files)
- **`README.md`**: Removed Kiro from platform list (3 places)
- **`README.zh-CN.md`**: Removed Kiro from platform list + `--platform kiro` example
- **`README.ja-JP.md`**: Removed Kiro from platform list + `--platform kiro` example
- **`README.ko-KR.md`**: Removed Kiro from platform list + `--platform kiro` example
- **`README.hi-IN.md`**: Removed Kiro from platform list + `--platform kiro` example
- **`CLAUDE.md`**: Removed Kiro from project overview
- **`docs/USAGE.md`**: Removed Kiro row from platform config table
- **`diagrams/generate_diagrams.py`**: Removed Kiro row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Kiro from supported list

## Verification
- 192 tests passed
- Ruff lint: all checks passed
- Zero `kiro` references in Python files
