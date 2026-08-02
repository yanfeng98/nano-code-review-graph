# 006 — Remove Antigravity Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Antigravity platform integration code. Antigravity was simple — PLATFORMS entry, MCP config, instruction files (AGENTS.md co-owner, GEMINI.md sole owner). Key decision: GEMINI.md was removed entirely since no other platform owns it after antigravity removal.

## Changes

### Core code (2 files)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["antigravity"]` entry
  - Updated `_PLATFORM_INSTRUCTION_FILES`: removed `antigravity` from AGENTS.md owners → `("opencode", "codex")`, removed `GEMINI.md` entirely
  - Updated `inject_platform_instructions` docstring
- **`code_review_graph/cli.py`**:
  - Removed `"antigravity"` from `_PLATFORM_CHOICES`

### Tests (1 file)
- **`tests/test_skills.py`**:
  - Deleted `test_antigravity_writes_agents_and_gemini`
  - Removed antigravity override from `test_install_all_detected`
  - Removed `"GEMINI.md"` from all expected sets and assertions (4 places)

### Documentation (9 files)
- **`README.md`**: Removed Antigravity from platform list (3 places)
- **`README.zh-CN.md`**: Removed Antigravity from platform list
- **`README.ja-JP.md`**: Removed Antigravity from platform list
- **`README.ko-KR.md`**: Removed Antigravity from platform list
- **`README.hi-IN.md`**: Removed Antigravity from platform list
- **`docs/USAGE.md`**: Removed Antigravity row
- **`diagrams/generate_diagrams.py`**: Removed Antigravity row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Antigravity from supported list

## Verification
- 148 tests passed
- Ruff lint: all checks passed
- Zero `antigravity` references in Python files
