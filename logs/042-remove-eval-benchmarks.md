# 042 — Remove Eval Benchmarks

**Date:** 2026-08-09
**Branch:** 260802-v2.3.7

## Summary

Removed the entire evaluation framework (`code-review-graph eval`). The command
clones 5 upstream GitHub benchmark repos (fastapi/flask/express/httpx/own) with
full clones and runs scoring benchmarks — but this fork's network cannot reach
GitHub, so `eval --all` hangs silently on the first clone. The user trusts the
context-savings claim and has no use for the benchmark harness, so the feature
is removed wholesale: code, CLI, tests, CI workflow, benchmark data,
documentation, and diagrams. **Runtime/MCP features are unaffected** — eval was
CLI-only.

Kept (independent features, NOT eval):
- `context_savings` metadata (`code_review_graph/context_savings.py`), incl.
  `estimate_tokens` — the runtime feature that reports per-call savings
- `detect-changes --brief --verify` / `update --brief --verify` — tiktoken
  cross-check of the Token Savings panel (optional `pip install tiktoken`)
- `matplotlib` in `exports.py` SVG export (already manual-install)
- `pyyaml` base dependency (pyproject line 33, untouched)

## Changes

### Core code (2 files)
- **`code_review_graph/eval/`** — deleted the entire package
  (`__init__.py`, `reporter.py`, `runner.py`, `scorer.py`,
  `token_benchmark.py`, `benchmarks/` ×8, `configs/` ×5 yaml)
- **`code_review_graph/token_benchmark.py`** — deleted (standalone token
  benchmark; only in-package importer was `eval/benchmarks/agent_baseline.py`)
- **`code_review_graph/cli.py`**:
  - Removed `eval` from the usage help string
  - Removed the `eval_cmd` parser block (`--benchmark`, `--repo`, `--all`,
    `--report`, `--output-dir`, `--embed`, `--embed-provider`,
    `--embed-model`)
  - Removed the `if args.command == "eval":` handler (lazy imports of
    `.eval.reporter` / `.eval.runner`)
- **`code_review_graph/embeddings.py`** — reworded the `_node_to_text`
  docstring to drop the ``multi_hop_retrieval`` / ``docs/REPRODUCING.md``
  reference

### Tests (2 files)
- **`tests/test_eval.py`** — deleted (1273 lines)
- **`tests/test_documentation.py`** — removed `"eval"` from `OPTIONAL_GROUPS`
  (so the pip-extra assertion no longer demands `pip install "code-review-graph[eval]"` in README)

### Packaging (2 files)
- **`pyproject.toml`** — removed the `eval = ["matplotlib>=3.7.0", "pyyaml>=6.0"]`
  extra; removed `code-review-graph[eval]` from `all`
- **`uv.lock`** — regenerated (`uv lock`); matplotlib + transitive deps dropped

### CI (1 file)
- **`.github/workflows/eval.yml`** — deleted the weekly eval cron

### Data (1 dir)
- **`evaluate/`** — deleted (15 tracked result CSVs + untracked `test_repos/`)

### Documentation (12 files)
- **`docs/REPRODUCING.md`** — deleted (entire doc was the eval methodology)
- **`README.md`** — removed the `## 基准测试` chapter (diagram5 image, 71x/528x
  claims, token_benchmark table, agent_baseline/token_efficiency discussion,
  impact/build/limitations sections, REPRODUCING.md links); removed the
  REPRODUCING nav link, the `Token 基准测试` feature row, the `code-review-graph eval`
  CLI line, `pip install "code-review-graph[eval]"`, and the `[all]` comment;
  rewrote the hero-image alt text to drop the benchmark claim. Kept the
  context-savings / Token Savings / `--verify` content.
- **`docs/USAGE.md`** — dropped the benchmark claim + links from the review-changes
  section; removed the `eval --all` block from the Context Savings section
  (kept the `--verify` / tiktoken / ~4% text)
- **`docs/COMMANDS.md`** — removed the `# 评估` header and `code-review-graph eval` line
- **`docs/LLM-OPTIMIZED-REFERENCE.md`** — removed `eval|` from the CLI list
- **`docs/FEATURES.md`** — removed eval changelog entries (agent_baseline,
  weekly eval CI, impact_accuracy co-change, deterministic pipeline,
  multi_hop_retrieval, path-normalization, FTS5 rebuild, evaluation framework,
  `[eval]` dep group); reworded the search-ranking bullet to drop benchmark numbers
- **`docs/FAQ.md`** — removed eval/benchmark paragraphs and REPRODUCING links;
  reworded the multi-hop, RAG-weakness, honest-numbers, when-not-to-use, and
  file-size guidance to stand without benchmark evidence
- **`docs/GITHUB_ACTION.md`** — removed the REPRODUCING calibration link
- **`docs/ROADMAP.md`** — removed eval entries; dropped the REPRODUCING link from
  the `--verify` bullet
- **`docs/TROUBLESHOOTING.md`** — removed the `pip install "code-review-graph[eval]"` bullet
- **`docs/INDEX.md`** — removed the REPRODUCING.md entry
- **`CLAUDE.md`** — removed `eval` from the CLI command list and the
  `uv run code-review-graph eval` line; removed the `tests/test_eval.py` entry.
  Kept the `No eval()` security invariant (the Python builtin, not this feature).

### Diagrams (3 files)
- **`diagrams/generate_diagrams.py`** — removed the `d5()` function and its
  registration; removed the REPRODUCING.md footnote
- **`diagrams/diagram5_benchmark_board.png`** — deleted
- **`diagrams/context-savings-demo.tape`** — deleted (depended on the removed
  `evaluate/test_repos/flask`); the committed `context-savings-demo.gif` is kept

### Local generated output (not git-tracked)
- **`.code-review-graph/wiki/eval-benchmark.md`** and stale eval references in
  other wiki pages — removed; wiki regenerated after the graph dropped the eval
  nodes (`code-review-graph update` + `wiki --force`)

### Not changed
- **`CHANGELOG.md`**, **`docs/MAINTAINER_RECONCILIATION_2026-07-17.md`**,
  **`logs/`** — historical records, left as-is
- **`tests/test_tools.py`** comment "as eval repos currently do" — harmless
- `.serena/project.yml`, `action.yml`, other `.github/workflows/*` — no eval refs

## Verification
- `grep` for `code_review_graph.eval`, `run_eval`, `eval_cmd`,
  `Run evaluation`, `code-review-graph eval`, `REPRODUCING`, `evaluate/`,
  `[eval]`, `token_benchmark`, `agent_baseline`, `multi_hop` → 0 hits in code,
  tests, CI, packaging, and docs (only `CHANGELOG.md` / `logs/` / historical
  docs retain the term)
- Runtime: `import code_review_graph` OK; `estimate_tokens` still resolves from
  `.context_savings`; `detect-changes --brief --verify` still prints the Token
  Savings panel (tiktoken optional)
- CLI: `code-review-graph --help` shows no `eval`; `code-review-graph eval`
  exits with an argparse unknown-command error
- Full suite: 1674 passed, 5 skipped (test_eval.py's 48 tests removed)
- Packaging: `uv lock --check` passes; `uv build` succeeds; sdist contains no
  eval modules or REPRODUCING.md
- Graph: incremental update dropped the eval nodes (3744 → 3611); no eval
  communities remain; wiki regenerated with zero eval references
