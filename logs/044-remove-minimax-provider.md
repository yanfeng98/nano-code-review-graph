# 044 — Remove MiniMax Embedding Provider

**Date:** 2026-08-09
**Branch:** 260802-v2.3.7

## Summary

Removed the MiniMax embedding provider — the last of four embedding providers
(local / openai / google / minimax) after Voyage was removed in `043` —
leaving three: `local`, `openai`, `google`. MiniMax was a **released** feature
(shipped since v2.0.0, `CHANGELOG.md:859`, `docs/ROADMAP.md:59`), so this is a
real feature removal: the CHANGELOG gains a `Removed` bullet and historical
entries are left intact. MiniMax had **no pip extra** (pure stdlib `urllib`),
so packaging is untouched. The provider was removed wholesale: class,
`get_provider` dispatch, the `refresh_embeddings` special-case, validation
entries, CLI choices, MCP docstrings, tests, and documentation. **Runtime /
MCP / CLI core are unaffected** — the other three providers and all shared
embedding helpers are intact.

Differences vs the Voyage removal (`logs/043`):
- MiniMax was **released** → `[Unreleased]` `### Removed` bullet, history kept
  (`CHANGELOG.md:684, :859`, `docs/ROADMAP.md:59`).
- `refresh_embeddings()` had a **MiniMax-only branch** (identity format
  `minimax:embo-01` needs a model-match check) — removed.
- More docs referenced MiniMax than Voyage: `CLAUDE.md`, `docs/FAQ.md`,
  `docs/TROUBLESHOOTING.md`, `SECURITY.md`, and the README feature-table row.
- `test_accept_env_var_suppresses_warning` was the only test of the
  `CRG_ACCEPT_CLOUD_EMBEDDINGS=1` suppression mechanism — **converted to the
  google provider** rather than deleted, preserving that coverage.

Kept (shared, NOT MiniMax):
- `OpenAIEmbeddingProvider._make_host_key` — still used by the OpenAI provider
- `_USER_AGENT` (OpenAI), `module logger`, `_is_localhost_url` (openai branch),
  `_warn_cloud_egress` (openai + google), `EmbeddingStore`, and the
  `get_provider("local")` fallback — all shared and still live

## Changes

### Core code (4 files)
- **`code_review_graph/embeddings.py`**
  - Removed the `MiniMaxEmbeddingProvider` class (`https://api.minimax.io/v1/embeddings`,
    `embo-01`, 1536-dim, `db`/`query` task types, retry logic, `_USER_AGENT` header)
  - Removed the `get_provider` `"minimax"` dispatch branch (`MINIMAX_API_KEY` +
    `_warn_cloud_egress("minimax")`)
  - Removed the `refresh_embeddings` `if provider == "minimax":` model-match
    branch
  - `_VALID_PROVIDERS` → `{"local", "openai", "google"}`;
    `CLOUD_PROVIDERS` → `{"google", "openai"}` (dead-code entry dropped)
  - Module docstring renumbered (item 3 removed, "4. OpenAI-compatible" → "3.");
    `get_provider` docstring and the error string now read
    `"Valid: local, openai, google"`
- **`code_review_graph/cli.py`** — `_add_embedding_refresh_args` and
  `embed --provider` `choices` → `{local, openai, google}`; `embed --model`
  help dropped `/minimax`
- **`code_review_graph/main.py`** — `semantic_search_nodes_tool` and
  `embed_graph_tool` docstrings dropped `minimax`
- **`code_review_graph/tools/docs.py`** — `embed_graph` docstring, the
  cloud-branch tuple (`if provider in ("openai", "google")`), and the
  "switch provider" hint dropped `minimax`

### Tests (2 files)
- **`tests/test_embeddings.py`** — removed `test_case_normalized_for_minimax`,
  `test_minimax_triggers_stderr_warning`, the `TestMiniMaxEmbeddingProvider`
  class (6 tests), and the `TestGetProviderMiniMax` class (2 tests); removed
  the `MiniMaxEmbeddingProvider` import and the valid-names assertion; converted
  `test_accept_env_var_suppresses_warning` from minimax → google
- **`tests/test_tools.py`** — updated the valid-providers assertion string

### Documentation (11 files)
- **`README.md`** — removed `MiniMax` from the feature-table 语义搜索 row and
  the `MINIMAX_API_KEY` env-table row
- **`docs/LLM-OPTIMIZED-REFERENCE.md`** — embeddings section provider list
  (this file is force-included in the wheel and served by `get_docs_section`)
- **`docs/COMMANDS.md`** — `provider` param lists (2)
- **`docs/USAGE.md`** — provider enumeration
- **`docs/LEGAL.md`** — cloud provider list in the egress bullet
- **`docs/FAQ.md`** — Cloud embeddings bullet provider list
- **`docs/TROUBLESHOOTING.md`** — optional-deps install list
- **`SECURITY.md`** — Cloud embeddings bullet
- **`CLAUDE.md`** — architecture section `embeddings.py` description
- **`CHANGELOG.md`** — added a `[Unreleased]` `### Removed` bullet for MiniMax
  (historical `:684`, `:859` entries kept)
- **`logs/043-remove-voyage-provider.md`** — untouched historical record

### Not changed
- **`pyproject.toml`** — no MiniMax extra existed (pure stdlib `urllib`); the
  `all` / `embeddings` / `google-embeddings` extras are untouched
- **Shared helpers**: `_make_host_key`, `_USER_AGENT`, `_is_localhost_url`,
  `_warn_cloud_egress`, `EmbeddingStore`, and the `get_provider("local")`
  fallback (returns `None` when `sentence-transformers` is not installed —
  unchanged pre-existing behavior)
- **`local` / `openai` / `google`** providers and their tests
- **`docs/FEATURES.md`**, **`docs/ROADMAP.md:59`** (v2.0.0 historical), and
  **`docs/FAQ.md`** beyond the one bullet — no further changes needed
- **`skills/`**, `prompts.py`, `hints.py`, `.github/` — no MiniMax references

## Verification
- `rg -i "minimax"` → only historical records remain: `CHANGELOG.md:28` (new
  Removed bullet), `:684/:859` (released history), `logs/043`, `docs/ROADMAP.md:59`
- Full suite: **1605 passed, 5 skipped** (10 MiniMax tests removed,
  `test_accept_env_var_suppresses_warning` converted to google)
- `ruff check code_review_graph/` and `mypy` → clean
- CLI: `code-review-graph embed --help` shows `--provider {local,openai,google}`;
  `code-review-graph embed --provider minimax` exits with an argparse
  invalid-choice error
- `get_provider("minimax")` → `ValueError("Unknown embedding provider 'minimax'.
  Valid: local, openai, google")`; `local` / `openai` / `google` resolve as before
- MCP `get_docs_section(embeddings)` returns the updated 3-provider list
- `code-review-graph status` OK (graph unaffected)
