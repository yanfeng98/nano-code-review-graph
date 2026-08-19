# 源码学习指南

> 目标读者：想学习本项目源码、之后要做魔改的开发者。
> 本文档从"外到内"组织，先跑起来、再读数据流主线、然后用图谱工具导航、最后逐模块深入。

## 1. 项目是什么（当前状态）

`code-review-graph` 是一个**本地优先、增量更新**的代码知识图谱，为 AI 编码工具（Claude Code、Codex、OpenCode）提供 token 高效的代码审查上下文。它用 Tree-sitter 把代码库解析成结构化图谱存进 SQLite，再通过 **CLI** 和 **MCP server** 暴露给 agent。

**当前形态（v2.3.7 分支）**：
- 纯 Python 核心，**无 VS Code 扩展**（已移除），专注 CLI/MCP 路线
- 图谱实测：~3275 节点 / ~30041 边 / 150 文件，风险 low
- 近期在持续精简：已移除多个 embedding provider、GitHub Action、eval 基准

```
源码 → [Tree-sitter 解析] → nodes/edges → [SQLite graph.db] → [MCP tools / CLI] → agent
```

## 2. 宏观地图

`code_review_graph/` 按职责分为几层（38 个模块文件 + `tools/` 子包）：

| 层级 | 模块 | 作用 |
|---|---|---|
| **解析层** | `parser.py`、`custom_languages.py`、`python_resolver.py`、`jedi_resolver.py`、`scoped_resolver.py`、`tsconfig_resolver.py` | 源码 → AST → 节点/边；语言与符号解析 |
| **存储层** | `graph.py`、`graph_diff.py` | SQLite 表结构、CRUD、BFS 影响分析 |
| **增量层** | `incremental.py`、`forget.py` | git 变更检测、增量重建、删除文件 |
| **分析层** | `changes.py`、`flows.py`、`communities.py`、`postprocessing.py`、`refactor.py`、`hints.py`、`analysis.py`、`context_savings.py` | 风险评分、执行流、社区聚类、重构建议、token 节省估算 |
| **搜索/嵌入** | `search.py`、`embeddings.py`、`enrich.py` | FTS5 混合搜索、向量嵌入、符号富化 |
| **服务层** | `main.py`、`tools/`、`prompts.py` | FastMCP server 入口、30 个 MCP 工具、5 个提示模板 |
| **CLI/平台** | `cli.py`、`uninstall.py`、`daemon.py`、`daemon_cli.py`、`skills.py`、`registry.py`、`constants.py` | 命令入口、安装/卸载、watch daemon、skill 生成、多仓库 |
| **可视化/导出** | `visualization.py`、`exports.py`、`wiki.py` | D3 HTML 图、导出、markdown wiki |
| **安全** | `http_origin_guard.py` | 服务端请求来源校验 |

## 3. 学习路径（四步）

### 步骤一：跑起来（~30 分钟）

```bash
uv sync --extra dev
uv run code-review-graph build              # 全量解析 → .code-review-graph/graph.db
uv run code-review-graph status             # 节点/边/文件统计
uv run code-review-graph detect-changes     # 风险评分变更分析（agent 主力用法）
uv run code-review-graph serve              # 起 MCP server
```

**强烈建议**：`sqlite3 .code-review-graph/graph.db` 看 `nodes`/`edges` 表结构——一切设计都围绕这两张表。

### 步骤二：数据流主线（核心，3-4 小时）

按真实执行顺序读这 6 个文件，**每个都配对应测试**：

| 顺序 | 文件 | 要回答的问题 | 对应测试 |
|---|---|---|---|
| 1 | `cli.py` | 命令如何分派？`build`/`update`/`detect-changes` 各调谁 | `test_cli.py` |
| 2 | `parser.py` | 源文件怎么变 AST、再变节点/边（**最重要**，~1300+ 行） | `test_parser.py`、`test_multilang.py` |
| 3 | `graph.py` | 表结构、节点/边存取、BFS 影响半径 | `test_graph.py` |
| 4 | `incremental.py` | 怎么只解析变更文件（git diff） | `test_incremental.py` |
| 5 | `changes.py` | 变更如何被风险评分 | `test_changes.py` |
| 6 | `main.py` + `tools/` | 30 个 MCP 工具如何注册暴露 | `test_tools.py` |

> 读 `parser.py`/`graph.py` 时并行看对应测试——测试是"需求文档"，告诉你每个函数该产出什么。

### 步骤三：用图谱工具导航（边学边检验）

本项目自带的 MCP 工具正好拿来导航，比人肉 grep 快：

| 图谱工具 | 用途 |
|---|---|
| `query_graph_tool(pattern="file_summary")` | 一次看某个文件全部节点 |
| `query_graph_tool(pattern="callers_of"/"callees_of")` | 追踪调用链 |
| `semantic_search_nodes("...")` | 按名字模糊找函数/类/测试 |
| `get_flow_tool("main")` | 看主流程完整调用路径 |
| `get_impact_radius_tool` | 改代码前看爆炸半径 |

示例：想找 `parse_file` → 搜到 `CodeParser.parse_file`（`parser.py:1315`）→ `callers_of` 找谁调它 → `get_flow` 看它在主流程位置。

### 步骤四：逐模块深入（按魔改方向）

主线读完后再按你的魔改目标进对应层级，见第 7 节。

## 4. 核心模块阅读指南

### 解析层（最值得细读）
- **`parser.py`**：核心。`CodeParser.parse_file()` 用 Tree-sitter 提取 AST，walker 按 `_CLASS_TYPES`/`_FUNCTION_TYPES`/`_IMPORT_TYPES`/`_CALL_TYPES` 映射提取节点和边。多语言靠 tree-sitter-language-pack。
- **`custom_languages.py`**：`.code-review-graph/languages.toml` 配置驱动的自定义语言（见 `docs/CUSTOM_LANGUAGES.md`）。
- **解析器们**：`python_resolver.py`（Python 导入/调用解析）、`jedi_resolver.py`（可选 jedi 富化）、`scoped_resolver.py`、`tsconfig_resolver.py`（TS path alias）。

### 存储层
- **`graph.py`**：`GraphStore`。`_SCHEMA_SQL` 一次性创建完整 schema、CRUD、`get_impact_radius()` BFS、旧库守卫。

### 增量层
- **`incremental.py`**：`get_changed_files()`（git diff）→ 找到依赖文件 → 只重解析变更部分（SHA-256 哈希跳过未变文件）。
- **`forget.py`**：`code-review-graph forget` 命令，从图谱剔除已解析文件。

### 分析层
- **`changes.py`**：风险评分（risk_score）、受影响函数/测试覆盖缺口。`detect-changes` 的核心。
- **`flows.py`**：执行流检测 + criticality 评分。
- **`communities.py`**：Leiden 或文件分组社区检测。
- **`postprocessing.py`**：flows/communities/FTS 后处理。
- **`refactor.py`**：重命名预览、死代码检测、重构建议。
- **`hints.py`**：review hint 生成。

### 服务层
- **`main.py`**：FastMCP server 入口，注册 30 工具 + 5 prompts。
- **`tools/`**：按域拆分的工具实现（`query.py`/`review.py`/`analysis_tools.py`/`community_tools.py`/`flows_tools.py`/`refactor_tools.py`/`registry_tools.py`/`build.py`/`docs.py`/`context.py`）。
- **`prompts.py`**：review_changes、architecture_map 等模板。
- **`search.py`**：FTS5 混合搜索；**`embeddings.py`**：可选向量嵌入（local/openai）。

### CLI/平台
- **`cli.py`**：所有子命令（install/init, build, update, postprocess, embed, watch, status, visualize, serve/mcp, wiki, detect-changes, register, unregister, repos, daemon, forget, uninstall）。
- **`skills.py`**：多平台 MCP 配置生成 + 自带 skill 元数据。
- **`registry.py`**：多仓库注册表；**`daemon.py`/`daemon_cli.py`**：watch daemon。

## 5. 测试结构导览

`tests/`（58 个测试文件，1601 passed）按模块对应，是理解每个模块最快的入口：

| 测试文件 | 覆盖 |
|---|---|
| `test_parser.py` / `test_multilang.py` / `test_custom_languages.py` | 解析正确性、多语言、自定义语言 |
| `test_graph.py` | 图谱 CRUD、统计、影响半径 |
| `test_incremental.py` / `test_forget.py` | 增量、删除 |
| `test_changes.py` / `test_flows.py` / `test_communities.py` | 风险评分、流程、社区 |
| `test_tools.py` / `test_prompts.py` | MCP 工具/提示集成 |
| `test_cli*.py` / `test_daemon.py` | CLI、daemon |
| `test_embeddings.py` / `test_search.py` | 嵌入、搜索 |
| `test_schema.py` | 新库 schema 完整性、旧库守卫 |
| `test_documentation.py` | 文档与实现一致性校验 |

**读法建议**：先读一个模块的测试，再看实现——测试里的断言就是模块的契约。

## 6. 安全不变量（魔改时不可违反）

- 无 `eval()`、`exec()`、`pickle`、`yaml.unsafe_load()`
- 无 `shell=True` 的子进程调用
- SQL 永远用参数化查询（`?` 占位符），绝不用 f-string 拼接值
- `_validate_repo_root()` 防 repo_root 路径穿越
- `_sanitize_name()` 消毒节点名（截断控制字符、限 256 字符，防 prompt injection）
- 可视化 HTML 转义（含引号/反引号），D3 CDN 带 SRI hash
- API key 只从环境变量读取

## 7. 魔改切入点（按需求）

| 想改什么 | 主攻文件 | 备注 |
|---|---|---|
| 加新语言支持 | `parser.py` + `custom_languages.py` + `docs/CUSTOM_LANGUAGES.md` | 修改 `EXTENSION_TO_LANGUAGE` 及 `_*_TYPES` 映射 |
| 改 MCP 工具行为 | `tools/` 对应文件 + `main.py` 注册 | 加工具要加测试 |
| 改影响分析/风险评分 | `graph.py` BFS + `changes.py` | 注意 blast radius 语义 |
| 加新分析维度 | 动 schema → `graph.py` 的 `_SCHEMA_SQL` | schema 变更后需删除 `.code-review-graph/` 重建 |
| 改给 agent 的输出 | `changes.py` + `hints.py` + `prompts.py` | token 效率优先 |
| 改搜索/嵌入 | `search.py` + `embeddings.py` | |
| 改 CLI | `cli.py` + `constants.py` | |
| 加导出/可视化 | `exports.py` + `visualization.py` + `wiki.py` | |

**动手前**：用 `get_impact_radius_tool` 看改动波及哪些文件，避免改公共函数炸一片。

## 8. 移除/新增功能的惯例

仓库近期多次移除功能，流程固定（参考 `logs/045-remove-google-provider.md`、`logs/046-remove-vscode-extension.md`）：

1. 核心代码改动 + 对应测试改动
2. 同步所有文档：`README.md`、`docs/*.md`、`CLAUDE.md`、`SECURITY.md`、`CHANGELOG.md`
3. 新建 `logs/NNN-*.md` 记录（含 summary / changes / verification）
4. 若涉及依赖：更新 `pyproject.toml` + `uv lock`
5. CHANGELOG 只在 `[Unreleased]` 加条目，**历史条目不改写**

## 9. 常见坑与建议

1. **别一上来读 `tools/` 全部 30 个文件**——那是终端输出，先懂数据流主线。
2. **图谱数据**：搜索前若 `search_mode: "fts"`，说明没跑嵌入；要语义搜索先 `uv run code-review-graph embed`。
3. **本地产物**：`.code-review-graph/`（graph.db、graph.html）和 `logs/` 是 gitignore/历史，别误当源码。
4. **测试数量是红线**：魔改后 `uv run pytest tests/ --tb=short -q` 必须保持全绿（当前 1601 passed）。
5. **质量门**：`uv run ruff check code_review_graph/` + `uv run mypy code_review_graph/ --ignore-missing-imports --no-strict-optional`。
