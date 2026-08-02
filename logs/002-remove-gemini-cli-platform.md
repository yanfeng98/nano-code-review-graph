# 002 — Remove Gemini CLI Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all Gemini CLI platform integration code and documentation references. Unlike Qwen Code (001), Gemini CLI was deeply integrated with dedicated hooks, skills, instruction files, and uninstall cleanup. Antigravity (which shares `.gemini/` directory and `GEMINI.md`) was carefully preserved.

Note: Gemini embedding API model recommendations (e.g., `gemini-embedding-001`) were intentionally left in place — those are unrelated to the Gemini CLI platform.

## Changes

### Core code (3 files, 194 lines removed)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["gemini-cli"]` dictionary entry
  - Removed `_GEMINI_CLI_HOOK_FILENAMES` constant
  - Removed `install_gemini_cli_hooks()` function (~130 lines)
  - Removed `install_gemini_cli_skills()` function (~20 lines)
  - Updated `_PLATFORM_INSTRUCTION_FILES`: `"GEMINI.md": ("antigravity", "gemini-cli")` → `"GEMINI.md": ("antigravity",)`
- **`code_review_graph/cli.py`**:
  - Removed `"gemini-cli"` from `_PLATFORM_CHOICES`
  - Removed `install_gemini_cli_hooks` and `install_gemini_cli_skills` imports
  - Removed Gemini CLI skills install block (target check + function call)
  - Removed Gemini CLI hooks install block (target check + function call)
- **`code_review_graph/uninstall.py`**:
  - Removed dedicated gemini hooks cleanup block (16 lines referencing `skills._GEMINI_CLI_HOOK_FILENAMES`)

### Tests (2 files, 179 lines removed)
- **`tests/test_skills.py`**:
  - Deleted `TestGeminiCLIInstall` class (2 methods: hooks + skills)
  - Deleted `test_install_gemini_cli_config`
  - Deleted `test_gemini_cli_writes_only_gemini_md`
  - Deleted `test_install_gemini_cli_hooks_preserves_non_ascii_field`
  - Removed `install_gemini_cli_hooks`/`install_gemini_cli_skills` imports
  - Removed `"gemini-cli"` override from `test_install_all_detected`
- **`tests/test_uninstall.py`**:
  - Deleted `test_gemini_shared_settings_removes_mcp_and_owned_hooks`

### Documentation (10 files)
- **`README.md`**: Removed Gemini CLI from platform list (3 places)
- **`README.zh-CN.md`**: Removed Gemini CLI from platform list
- **`README.ja-JP.md`**: Removed Gemini CLI from platform list
- **`README.ko-KR.md`**: Removed Gemini CLI from platform list
- **`README.hi-IN.md`**: Removed Gemini CLI from platform list
- **`CLAUDE.md`**: Removed Gemini CLI from project overview
- **`docs/USAGE.md`**: Removed Gemini CLI row from platform config table
- **`docs/architecture.md`**: Removed Gemini CLI from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed Gemini CLI row
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Removed Gemini CLI from supported list

### Preserved
- `GEMINI.md` instruction file still generated for Antigravity
- `.gemini/skills/` cleanup loop in uninstall kept for backward compatibility
- Antigravity platform fully unaffected

## Verification

- 227 tests passed
- Ruff lint: all checks passed
- Zero `gemini-cli`/`gemini_cli`/`Gemini CLI` references in Python files
- Only `CHANGELOG.md` and `docs/ROADMAP.md` retain historical Gemini CLI mentions
