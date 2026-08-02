# 011 — Remove CodeBuddy Code Platform Support

**Date:** 2026-08-02
**Branch:** 260802-v2.3.7

## Summary

Removed all CodeBuddy Code platform integration. CodeBuddy shared `.mcp.json` with Claude Code (deduplication logic in `install_platform_configs`), and had dedicated hooks, skills, instruction file `CODEBUDDY.md`, and uninstall cleanup. The shared alias dedup logic was simplified — with only Claude Code remaining, the `shared_aliases` mechanism is no longer needed.

## Changes

### Core code (3 files)
- **`code_review_graph/skills.py`**:
  - Removed `PLATFORMS["codebuddy"]` entry
  - Removed Claude-CodeBuddy shared alias block (~17 lines); simplified `_record_configured`
  - Removed `"CODEBUDDY.md"` from `_PLATFORM_INSTRUCTION_FILES`
  - Removed `install_codebuddy_hooks()` function
  - Removed `install_codebuddy_skills()` function
- **`code_review_graph/cli.py`**:
  - Removed `"codebuddy"` from `_PLATFORM_CHOICES`
  - Removed `install_codebuddy_hooks`/`install_codebuddy_skills` imports
  - Removed skills install block and hooks install block
- **`code_review_graph/uninstall.py`**:
  - Removed CodeBuddy hooks cleanup
  - Changed skills cleanup loop: `(".claude", ".gemini", ".codebuddy")` → `(".claude", ".gemini")`

### Tests (4 files)
- **`tests/test_skills.py`**:
  - Deleted `TestCodeBuddyPlatform` class + 8 related test methods
  - Deleted `test_codebuddy_writes_only_codebuddy_md_and_is_idempotent`
  - Removed `"CODEBUDDY.md"` from instruction file expected sets
- **`tests/test_cli_install.py`**:
  - Deleted `test_handle_init_codebuddy_installs_only_codebuddy_native_files`
- **`tests/test_documentation.py`**:
  - Deleted `test_codebuddy_install_docs_cover_project_artifacts`
- **`tests/test_uninstall.py`**:
  - Removed `.codebuddy/skills` from generated roots list

### Documentation
- **`README.md`**: Removed CodeBuddy from platform list (3 places)
- i18n READMEs: already updated from Continue removal
- **`CLAUDE.md`**: Already correct from previous removals
- **`docs/USAGE.md`**: Removed CodeBuddy row and its dedicated documentation paragraph
- **`docs/architecture.md`**: Removed CodeBuddy from architecture overview
- **`diagrams/generate_diagrams.py`**: Removed CodeBuddy row, updated platform count comment
- **`.github/ISSUE_TEMPLATE/platform_request.yml`**: Already correct

## Verification
- 139 tests passed
- Ruff lint: all checks passed
- Zero `codebuddy` references in Python files
