# 045 — Remove Google Gemini Embedding Provider

**Date:** 2026-08-10
**Branch:** 260802-v2.3.7

## Summary

Removed the Google Gemini embedding provider — the last of three embedding
providers (local / openai / google) after Voyage (`043`) and MiniMax (`044`)
were removed — leaving two: `local`, `openai`. Google was a **released**
feature (since v1.8.3, `CHANGELOG.md:895`), so the CHANGELOG gains a `Removed`
bullet and historical entries stay. Unlike the prior two removals, Google
**had a pip extra** (`google-embeddings` → `google-generativeai`), so this
removal touched packaging: the extra was dropped from `pyproject.toml` and
`uv.lock` was regenerated. **Runtime / MCP / CLI core are unaffected** — the
two remaining providers and all shared embedding helpers are intact.

Differences vs the Voyage (`043`) / MiniMax (`044`) removals:
- **Packaging coupling (new)**: `pyproject.toml` `google-embeddings` extra
  removed; `uv.lock` regenerated (google-generativeai + ~10 transitive
  `google-*`/`grpcio-*`/`protobuf` packages pruned); `tests/test_documentation.py`
  dropped `"google-embeddings"` from `OPTIONAL_GROUPS`; the
  `pip install "code-review-graph[google-embeddings]"` lines removed from
  `README.md` and `docs/TROUBLESHOOTING.md`. The `all` extra did **not**
  reference `google-embeddings` — no `all` edit.
- **Platform vs provider**: the Gemini CLI *platform* was already removed
  (`logs/002`). The only remaining `.gemini` strings are the backward-compat
  uninstall cleanup loop (`uninstall.py:1048`) and its test
  (`test_uninstall.py:213`) — **platform, KEEP**.
- **Warning-test conversion**: removing google leaves `openai` as the only
  cloud provider. `test_google_triggers_stderr_warning` was deleted (openai
  already has equivalent coverage via `test_cloud_base_url_triggers_egress_warning`),
  and `test_accept_env_var_suppresses_warning` (the only test of
  `CRG_ACCEPT_CLOUD_EMBEDDINGS=1`) was **converted to openai**.
- `GEMINI.md` is a themed-codename doc (MCP tools reference) with no
  google/gemini content — **KEEP**, untouched.

Kept (shared, NOT Google):
- `OpenAIEmbeddingProvider._make_host_key`, `_USER_AGENT`,
  `_is_localhost_url` (openai branch), `_warn_cloud_egress` (openai branch),
  `EmbeddingStore`, and the `get_provider("local")` fallback — all shared and
  still live (google used a separate `google.genai.Client` path)

## Changes

### Core code (4 files)
- **`code_review_graph/embeddings.py`**
  - Removed the `GoogleEmbeddingProvider` class (`google.genai` client,
    `gemini-embedding-001`, `_call_with_retry` with exponential backoff,
    `google:{model}` identity)
  - Removed the `get_provider` `"google"` dispatch branch (`GOOGLE_API_KEY` +
    `_warn_cloud_egress("google")` + `try/except ImportError`)
  - `_VALID_PROVIDERS` → `{"local", "openai"}`; `CLOUD_PROVIDERS` → `{"openai"}`
  - Module docstring renumbered to 2 items (Local, OpenAI-compatible);
    `get_provider` docstring and the error string now read
    `"Valid: local, openai"`
- **`code_review_graph/cli.py`** — `_add_embedding_refresh_args` and
  `embed --provider` `choices` → `{local, openai}`; `embed --model` help
  dropped `/google`
- **`code_review_graph/main.py`** — `semantic_search_nodes_tool` and
  `embed_graph_tool` docstrings dropped `google` / `Gemini`
- **`code_review_graph/tools/docs.py`** — `embed_graph` docstring, the
  cloud-branch condition (`if provider == "openai"`), and the "switch provider"
  hint dropped `google`

### Packaging (2 files)
- **`pyproject.toml`** — removed the `google-embeddings = ["google-generativeai>=0.8.0,<1"]`
  extra; the `all` extra is untouched (it never referenced google-embeddings)
- **`uv.lock`** — regenerated via `uv lock`; pruned `google-generativeai`,
  `google-ai-generativelanguage`, `google-api-core`, `google-auth`,
  `googleapis-common-protos`, `grpcio-status`, `protobuf`, `requests`, and
  other transitive deps (~10 packages removed)

### Tests (3 files)
- **`tests/test_embeddings.py`** — removed the `GoogleEmbeddingProvider` import,
  the `TestGoogleEmbeddingProviderRetryLogging` class (3 tests), and
  `test_google_triggers_stderr_warning`; updated the valid-names assertion;
  converted `test_accept_env_var_suppresses_warning` from google → openai
- **`tests/test_tools.py`** — updated the valid-providers assertion string
- **`tests/test_documentation.py`** — removed `"google-embeddings"` from
  `OPTIONAL_GROUPS`

### Documentation (11 files)
- **`README.md`** — removed `Google Gemini` from the feature-table 语义搜索 row,
  the `pip install "code-review-graph[google-embeddings]"` line, the
  `GOOGLE_API_KEY` env-table row, and the `gemini-embedding-*`/`GOOGLE_API_KEY`
  model-tip blockquote
- **`docs/LLM-OPTIMIZED-REFERENCE.md`** — embeddings section provider list
  (this file is force-included in the wheel and served by `get_docs_section`)
- **`docs/COMMANDS.md`** — `provider` param lists (2)
- **`docs/USAGE.md`** — provider enumeration
- **`docs/LEGAL.md`** — cloud provider list in the egress bullet
- **`docs/FAQ.md`** — Cloud embeddings bullet provider list
- **`docs/TROUBLESHOOTING.md`** — removed the `google-embeddings` install line
- **`SECURITY.md`** — Cloud embeddings bullet
- **`CLAUDE.md`** — architecture section `embeddings.py` description
- **`CHANGELOG.md`** — added a `[Unreleased]` `### Removed` bullet for Google;
  updated the MiniMax bullet's "providers are now `local`, `openai`, and
  `google`" to `local`, `openai` (historical entries `:499/:684/:726/:895` kept)
- **`logs/044-remove-minimax-provider.md`** — untouched historical record

### Not changed
- **`local` / `openai`** providers and their tests
- **Platform code**: `uninstall.py:1048` (`.gemini` backward-compat cleanup),
  `test_uninstall.py:213`, `docs/ROADMAP.md:31` (Gemini CLI platform history)
- **Historical records**: `CHANGELOG.md:499/:684/:726/:895`,
  `docs/ROADMAP.md:60`, `docs/FEATURES.md:47/:63` (v2.0.0 / v1.8.3),
  `docs/MAINTAINER_RECONCILIATION_2026-07-17.md:91`, `logs/002/:006/:011/:043/:044`,
  `GEMINI.md` (codename doc)
- **Shared helpers**: `_make_host_key`, `_USER_AGENT`, `_is_localhost_url`,
  `_warn_cloud_egress`, `EmbeddingStore`, `get_provider("local")` fallback
- `skills/`, `AGENTS.md`, `CONTRIBUTING.md`, `.github/`, `code-review-graph-vscode/`

## Verification
- `rg -i "google-embeddings|GOOGLE_API_KEY|gemini-embedding|GoogleEmbeddingProvider|google-generativeai"`
  → only historical records remain: `CHANGELOG.md:32-35` (new Removed bullet),
  `docs/FEATURES.md:47`, `docs/ROADMAP.md:60` (v2.0.0), `logs/002/:043/:044`
- Full suite: **1601 passed, 5 skipped** (4 Google tests removed,
  `test_accept_env_var_suppresses_warning` converted to openai)
- `ruff check code_review_graph/` and `mypy` → clean
- `uv lock --check` → passes; `uv.lock` no longer contains google-generativeai
  or any google-* package
- CLI: `code-review-graph embed --help` shows `--provider {local,openai}`;
  `code-review-graph embed --provider google` exits with an argparse
  invalid-choice error
- `get_provider("google")` → `ValueError("Unknown embedding provider 'google'.
  Valid: local, openai")`; `local` / `openai` resolve as before
- MCP `get_docs_section(embeddings)` returns the updated 2-provider list
- `code-review-graph status` OK (graph unaffected)
