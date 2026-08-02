# 001 — Remove Qwen Code Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Qwen Code platform integration code and documentation references. The user does not use Qwen Code, and this cleanup ensures the project only maintains supported platforms.

Note: embedding model mentions (e.g., `Qwen/Qwen3-Embedding-8B`, `Qwen text-embedding-v4`) were intentionally left in place — those are model recommendations unrelated to the Qwen Code platform.

## Changes

### Core code
- **`code_review_graph/skills.py`**: Removed `PLATFORMS["qwen"]` dictionary entry (8 lines)
- **`code_review_graph/cli.py`**: Removed `"qwen"` from `_PLATFORM_CHOICES` list

### Tests
- **`tests/test_skills.py`**: Deleted `test_install_qwen_config` and `test_install_qwen_preserves_existing_servers` (2 test methods)
- **`tests/test_uninstall.py`**: Replaced `.qwen/settings.json` with `.kiro/settings/mcp.json` in `test_keep_flags_preserve_data_and_user_configuration`

### Documentation
- **`README.md`**: Removed Qwen from platform list (3 places)
- **`README.zh-CN.md`**: Removed Qwen from platform list
- **`README.ja-JP.md`**: Removed Qwen from platform list
- **`README.ko-KR.md`**: Removed Qwen from platform list
- **`README.hi-IN.md`**: Removed Qwen from platform list
- **`CLAUDE.md`**: Removed Qwen from project overview
- **`docs/USAGE.md`**: Removed Qwen Code row from platform config table
- **`docs/architecture.md`**: Removed Qwen from architecture overview

### Diagrams / Metadata
- **`diagrams/generate_diagrams.py`**: Removed Qwen Code row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Qwen from supported platforms list

## Verification

- 234 tests passed
- Ruff lint: all checks passed
- Grep confirmed no Qwen Code platform references remain (only CHANGELOG/ROADMAP historical records and embedding model recommendations)
