# 046 — Remove VS Code Extension

**Date:** 2026-08-10
**Branch:** 260802-v2.3.7

## Summary

Removed the VS Code extension (`code-review-graph-vscode/`, a TypeScript
subproject) — the visual/UI frontend that reads `.code-review-graph/graph.db`
directly via better-sqlite3 and renders tree views, D3 force-directed graphs,
and review guidance inside VS Code. The primary use case for this repo is now
driving **agents from the terminal** (MCP server + CLI), where the extension's
UI layer adds zero value.

The extension was a **released** feature (shipped to the VS Code Marketplace,
`code-review-graph-vscode/CHANGELOG.md`), so the CHANGELOG gains a `Removed`
bullet and historical entries stay. Unlike the embedding-provider removals
(`043`/`044`/`045`), this removal touches **no Python code and no packaging**:
`code_review_graph/` and `tests/` contain zero vscode references, and
`pyproject.toml`'s wheel/sdist never included the subproject. **Runtime / MCP /
CLI core are completely unaffected** — all 30 MCP tools and the CLI
(`build`/`update`/`detect-changes`/`serve`) are intact.

## Changes

### Deleted (1 directory, 32 files)
- **`code-review-graph-vscode/`** — entire subproject removed via `git rm -r`:
  - `src/` (extension.ts, backend/{sqlite,cli,watcher}.ts,
    features/{blastRadius,cursorResolver,navigation,reviewAssistant,
    scmDecorations,search}.ts, views/{treeView,graphWebview,statusBar,treeItems}.ts,
    onboarding/{welcome,installer}.ts, webview/graph.ts)
  - `test/sqlite.test.ts`, `media/` (icons, walkthrough markdown)
  - build/config: `package.json`, `package-lock.json`, `tsconfig.json`,
    `esbuild.mjs`, `.vscodeignore`, `.gitignore`, `CHANGELOG.md`, `README.md`,
    `LICENSE`

### CI (1 file)
- **`.github/workflows/ci.yml`** — removed the `schema-sync` job, which was the
  only CI that referenced the extension (it read
  `code-review-graph-vscode/src/backend/sqlite.ts` and compared the TS
  `SUPPORTED_SCHEMA_VERSION` against the Python `LATEST_VERSION`). Without the
  directory this job would fail on every run. `lint` / `type-check` /
  `security` / `test` / `windows-native` jobs are untouched; `publish.yml` had
  no vscode reference.

### Config (1 file)
- **`.gitignore`** — removed the `# VS Code extension build artifacts` block
  (`code-review-graph-vscode/dist/`, `*.vsix`). The generic `node_modules/`
  entry and IDE `.vscode/` entry are kept.

### Documentation (2 files)
- **`CLAUDE.md`** — dropped the `VS Code Extension` entry from the Architecture
  section (3 lines).
- **`CHANGELOG.md`** — added a `[Unreleased]` → `### Removed` bullet for the
  extension, noting the CLI/MCP server/30 tools are unaffected.

### New record
- **`logs/046-remove-vscode-extension.md`** — this file.

## Not changed

- **Python core** (`code_review_graph/`) — zero vscode references verified by
  grep; no edits needed.
- **Tests** (`tests/`) — zero vscode references; no test edits needed.
- **`README.md`** — no vscode/extension/marketplace/.vsix mentions.
- **`pyproject.toml`** — wheel/sdist never included the subproject.
- **`skills/`, `hooks/`, `AGENTS.md`, `SECURITY.md`, `CONTRIBUTING.md`,
  `.mcp.json`** — zero vscode references.
- **Historical records (kept)**: `CHANGELOG.md` historical bullets,
  `docs/FEATURES.md:57`, `docs/ROADMAP.md:34` (historical release notes),
  `docs/MAINTAINER_RECONCILIATION_2026-07-17.md:153` (one-off audit doc),
  `diagrams/generate_diagrams.py:568` (Excalidraw third-party tool comment),
  `logs/` prior records.

## Verification

- `rg -i "vscode|code-review-graph-vscode|vsce|\.vsix|VS Code"`
  (excluding `.venv`/`.git`/`logs`) → only historical docs remain:
  `CHANGELOG.md` (new Removed bullet + history), `docs/FEATURES.md`,
  `docs/ROADMAP.md`, `docs/MAINTAINER_RECONCILIATION_2026-07-17.md`,
  `diagrams/generate_diagrams.py` (comment)
- Full suite: pytest passes (no vscode tests to remove; count unchanged)
- `ruff check code_review_graph/` and `mypy` → clean
- CLI: `code-review-graph build` / `status` / `detect-changes` → OK (graph
  unaffected)
- `grep schema-sync .github/workflows/ci.yml` → no match (job gone)

## Deep audit (second pass)

A second audit re-verified every layer and probed two residual-flag concerns.
Result: **the removal is correct; no active documentation needed updating.**

### Re-verified clean
- Whole-repo grep (`vscode`/`code-review-graph-vscode`/`vsce`/`.vsix`/
  `VS Code`, case-insensitive, excluding `.venv`/`.git`/`logs`/
  `.code-review-graph`) matches only historical records.
- **`README.md`** — zero extension references. Its three "扩展" matches are
  language-extension names / parameter expansion, not the VS Code extension.
- **`publish.yml`** — publishes only to PyPI; no extension-publishing job.
- **`tests/test_skills.py`** — no copilot/vscode/extension content (the
  `.pytest_cache` nodeids mentioning `test_copilot_*` were stale cache from the
  pre-logs/007 copilot-platform era).
- **Active docs** (`docs/architecture.md`, `docs/INDEX.md`, `docs/COMMANDS.md`,
  `docs/USAGE.md`, `docs/FAQ.md`, `docs/TROUBLESHOOTING.md`, `docs/LEGAL.md`,
  `docs/schema.md`, `docs/CUSTOM_LANGUAGES.md`,
  `docs/LLM-OPTIMIZED-REFERENCE.md`, `CONTRIBUTING.md`, `AGENTS.md`,
  `SECURITY.md`, `skills/`, `hooks/`, `.mcp.json`) — zero VS Code extension
  references. `CLAUDE.md` / `CHANGELOG.md` / `ci.yml` were the only files
  carrying live references and are all updated in this commit.

### Residual-flag probes (both benign)
- **`grep -c vscode .code-review-graph/graph.db` → 3866** — a raw-file grep
  that looks alarming, but the graph tables are clean at query level:
  `SELECT COUNT(*) FROM nodes WHERE name/qualified_name/file_path LIKE
  '%vscode%'` → **0**, same for `edges` (0), and `nodes_fts MATCH 'vscode'` →
  **0**; `semantic_search_nodes_tool("vscode")` → **0 results**. The 3866
  raw-file hits are leftover disk pages inside SQLite free space (the rebuild
  overwrote the tables, not the whole file). They are invisible to every query
  path, so agent searches cannot surface stale extension nodes.
- **`.code-review-graph/graph.html` (Aug 9) still contains extension nodes** —
  `build` does not regenerate HTML; that is the `visualize` command's job, and
  the file is gitignored. Rerun `code-review-graph visualize` to refresh.

### Kept as history (per user decision — not rewritten)
- `docs/FEATURES.md:57`, `docs/ROADMAP.md:34` — versioned release notes.
- `docs/MAINTAINER_RECONCILIATION_2026-07-17.md:153` — one-off audit doc.
- `diagrams/generate_diagrams.py:568` — third-party (Excalidraw) comment.
- `CHANGELOG.md` historical bullets, `logs/` prior records.
