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
