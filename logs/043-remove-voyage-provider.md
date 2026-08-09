# 043 — Remove Voyage Embedding Provider

**Date:** 2026-08-09
**Branch:** 260802-v2.3.7

## Summary

Removed the Voyage AI embedding provider — one of five embedding providers
(local / openai / google / minimax / voyage) — leaving four. Voyage was added
under `[Unreleased]` and never shipped; it calls Voyage's cloud embeddings API
(`voyage-code-3`, `https://api.voyageai.com/v1`) using stdlib `urllib`. There
was **no pip extra** for Voyage, so packaging is untouched. The provider was
removed wholesale: class, `get_provider` dispatch, validation entries, CLI
choices, MCP tool docstrings, tests, and documentation. **Runtime / MCP /
CLI core are unaffected** — the other four providers and all shared embedding
helpers are intact.

Kept (shared, NOT Voyage):
- `OpenAIEmbeddingProvider._make_host_key` — still used by the OpenAI provider
- `_USER_AGENT`, module `logger`, `_is_localhost_url`, `_warn_cloud_egress`,
  `EmbeddingStore`, the local fallback (`get_provider("local")`) — all shared
- The general embedding improvement "Embeddings are now persisted after each
  batch for every provider" (`CHANGELOG.md` [Unreleased], #783) — a shared
  feature that happened to live in the same changelog bullet

## Changes

### Core code (4 files)
- **`code_review_graph/embeddings.py`**
  - Removed the `VoyageEmbeddingProvider` class (document/query input types,
    `output_dimension`/`output_dtype`, batch pacing, index-order misalignment
    guards, exponential-backoff retries)
  - Removed the `get_provider` `"voyage"` dispatch branch (reads `VOYAGE_API_KEY`,
    `CRG_VOYAGE_BASE_URL`/`_MODEL`/`_OUTPUT_DIMENSION`/`_OUTPUT_DTYPE`/
    `_BATCH_SIZE`/`_MIN_INTERVAL_SEC`, plus `_warn_cloud_egress("voyage")`)
  - `_VALID_PROVIDERS` → `{"local", "openai", "google", "minimax"}`
  - `CLOUD_PROVIDERS` → `{"google", "minimax", "openai"}` (dead-code entry dropped)
  - Module docstring dropped item 5; `get_provider` docstring and the error
    string now read `"Valid: local, openai, google, minimax"`
- **`code_review_graph/cli.py`** — `_add_embedding_refresh_args` and
  `embed --provider` `choices` → `{local, openai, google, minimax}`; `embed
  --model` help dropped `/voyage`
- **`code_review_graph/main.py`** — `semantic_search_nodes_tool` and
  `embed_graph_tool` docstrings dropped `voyage` and `CRG_VOYAGE_MODEL`
- **`code_review_graph/tools/docs.py`** — `embed_graph` docstring, the
  cloud-branch tuple (`if provider in ("openai", "google", "minimax")`), and
  the "switch provider" hint dropped `voyage`

### Tests (2 files)
- **`tests/test_embeddings.py`** — removed `_make_voyage_response`, the
  `TestVoyageEmbeddingProvider` class (8 tests), the `TestGetProviderVoyage`
  class (4 tests), the `VoyageEmbeddingProvider` import, the valid-names
  assertion, and a comment mention of `voyage-3`
- **`tests/test_tools.py`** — updated the valid-providers assertion string

### Documentation (6 files)
- **`README.md`** — removed 7 env-table rows (`VOYAGE_API_KEY`, `CRG_VOYAGE_*`)
  and the Voyage usage section; `CRG_ACCEPT_CLOUD_EMBEDDINGS` stays in the
  env table
- **`docs/LLM-OPTIMIZED-REFERENCE.md`** — embeddings section provider list and
  env note (this file is force-included in the wheel and served by
  `get_docs_section`)
- **`docs/COMMANDS.md`** — `provider` param lists (2)
- **`docs/USAGE.md`** — provider enumeration + Voyage env sentence
- **`docs/LEGAL.md`** — cloud provider list in the egress bullet
- **`CHANGELOG.md`** — removed the `[Unreleased]` "Added a Voyage AI embedding
  provider" bullet; **kept** the shared "Embeddings are now persisted after
  each batch for every provider" improvement (#783)

### Not changed
- **`pyproject.toml`** — no Voyage extra existed (pure stdlib `urllib`); the
  `all` / `embeddings` / `google-embeddings` extras are untouched
- **Shared helpers**: `_make_host_key`, `_USER_AGENT`, `_is_localhost_url`,
  `_warn_cloud_egress`, `EmbeddingStore`, and the `get_provider("local")`
  fallback (returns `None` when `sentence-transformers` is not installed —
  unchanged pre-existing behavior)
- **`local` / `openai` / `google` / `minimax`** providers and their tests
- **`docs/FEATURES.md`**, **`docs/ROADMAP.md`**, **`docs/FAQ.md`** — already
  had no Voyage references
- **`skills/`**, `prompts.py`, `hints.py`, `.github/`, earlier **`logs/`** —
  no Voyage references, left as-is

## Verification
- `rg -i "voyage"` → **0 hits** repo-wide
- Full suite: **1615 passed, 5 skipped** (12 Voyage tests removed)
- `ruff check code_review_graph/` and `mypy` → clean
- CLI: `code-review-graph embed --help` shows `--provider {local,openai,google,minimax}`;
  `code-review-graph embed --provider voyage` exits with an argparse
  invalid-choice error
- `get_provider("voyage")` → `ValueError("Unknown embedding provider 'voyage'.
  Valid: local, openai, google, minimax")`; `local` / `openai` / `google` /
  `minimax` resolve exactly as before
- MCP `get_docs_section(embeddings)` returns the updated provider list
- `code-review-graph status` OK (graph unaffected)
