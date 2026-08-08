# 架构

## 系统概览

`code-review-graph` 是一个本地优先的代码智能图（code intelligence graph），通过 CLI 和 MCP server 暴露。它维护代码库的持久化、增量更新的知识图谱，使 AI 编码工具能够以结构性上下文审查变更，而不是阅读大段的文件转储。Claude Code 受支持，但它只是众多 client 之一。

## 组件图

```
┌──────────────────────────────────────────────────────────────┐
│                    AI coding clients / CLI                    │
│                                                              │
│  MCP clients              Hooks / watch mode                 │
│  ├── Codex                └── incremental update             │
│  ├── Claude Code                             │
│  └── OpenCode              │
│          │                        │                          │
│          ▼                        ▼                          │
│  ┌────────────────────────────────────────────┐              │
│  │      MCP Server (stdio or localhost HTTP)  │              │
│  │                                            │              │
│  │  30 MCP Tools + 5 MCP Prompts              │              │
│  │  ├── Core: build, impact, query, review,   │              │
│  │  │   search, traverse, embed, stats, docs  │              │
│  │  ├── Flows: list, get, affected            │              │
│  │  ├── Communities: list, get, architecture  │              │
│  │  ├── Analysis: detect_changes, refactor,   │              │
│  │  │   apply_refactor, hotspots, gaps        │              │
│  │  ├── Wiki: generate, get_page              │              │
│  │  └── Multi-repo: list_repos, cross_search  │              │
│  └────────────────┬───────────────────────────┘              │
└───────────────────┼──────────────────────────────────────────┘
                    │
        ┌───────────┼───────────────┐
        ▼           ▼               ▼
   ┌─────────┐ ┌─────────┐  ┌─────────────┐
   │ Parser  │ │  Graph  │  │ Incremental │
   │         │ │  Store  │  │   Engine    │
   └────┬────┘ └────┬────┘  └──────┬──────┘
        │           │              │
        ▼           ▼              ▼
   Tree-sitter   SQLite DB      git/svn diff
   grammars      (.code-review- subprocess
                 graph/
                 graph.db)
```

## 数据流

### 完整 Build
1. `collect_all_files()` 收集已跟踪的文件（`git ls-files`）并应用 `.code-review-graphignore`（git 可用时 gitignored 文件会被自动跳过）
2. 对每个文件，`CodeParser.parse_file()` 使用 Tree-sitter 提取 AST
3. AST walker 识别结构 nodes（classes、functions、imports）和 edges（calls、inheritance）
4. `GraphStore.store_file_nodes_edges()` 持久化到 SQLite，带用于变更检测的文件 hash
5. 用时间戳更新 metadata

### 增量更新
1. `get_changed_files()` 使用 VCS 元数据识别变更的文件（默认 git diff，增量层支持 SVN）
2. `find_dependents()` 查询 graph 中导入这些变更文件的文件
3. 重新解析变更 + 依赖的文件（其他文件通过 hash 比较跳过）
4. 只更新 SQLite 中受影响的行

### Review Context 生成
1. 识别变更的文件（git diff 或显式列表）
2. `get_impact_radius()` 从变更 nodes 出发在 graph 中执行 BFS
3. 只为变更区域提取源码片段
4. 生成 review 指导（测试覆盖缺口、宽 blast radius 警告）
5. 组装成结构紧凑、token 高效的 context，供 MCP clients 和 CLI 使用
6. 在能估算廉价 baseline 的地方，附加紧凑的 `context_savings` 元数据作为估算，而非精确 tokenisation

## 存储

### SQLite Schema
- **nodes** 表：id、kind、name、qualified_name、file_path、line_start/end、language、community_id 等。
- **edges** 表：id、kind、source_qualified、target_qualified、file_path、line
- **metadata** 表：key-value 对（last_updated、build_type、schema_version）
- **flows** 表：id、name、entry_point_id、depth、node_count、file_count、criticality、path_json
- **flow_memberships** 表：flow_id、node_id、position
- **communities** 表：id、name、level、parent_id、cohesion、size、dominant_language、description
- **nodes_fts**（FTS5 虚拟表）：对 name、qualified_name、file_path、signature 的全文搜索
- **community_summaries**、**flow_snapshots**、**risk_index** 表：用于 token 高效查询的紧凑预计算摘要
- **embeddings** 表（单独的 DB）：qualified_name、vector、text_hash、provider

对 qualified_name、file_path、edge source/target、criticality、community_id 和 cohesion 建立索引，以实现快速查找。

启用 WAL 模式，以便在更新期间进行并发读访问。

### Qualified Names
Nodes 由 qualified names 唯一标识：
- 文件：绝对路径（例如 `/repo/src/auth.py`）
- 函数：`file_path::function_name`（例如 `/repo/src/auth.py::authenticate`）
- 方法：`file_path::ClassName.method_name`（例如 `/repo/src/auth.py::AuthService.login`）

## 解析策略

Tree-sitter 提供与语言无关的 AST 访问。Parser：
1. 递归遍历 AST
2. 在 node types 上做 pattern 匹配（语言专属映射在 `_CLASS_TYPES`、`_FUNCTION_TYPES` 等中）
3. 提取名称、参数、返回类型、基类
4. 识别函数体内的 calls
5. 把 imports 解析为模块路径

这种方法比跨 grammar 版本使用 tree-sitter queries 更稳健。

## 可视化

`visualization.py` 模块生成一个自包含 HTML 文件形式的交互式 D3.js force-directed graph。它从 SQLite graph store 读取所有 nodes 和 edges，并在浏览器中渲染，让开发者能够可视化地探索代码关系、按 node kind 过滤，并检查依赖。

## 影响分析算法

从种子 nodes（变更文件的内容）出发进行 BFS：
1. 种子 = 变更文件中的所有 qualified names
2. 对 frontier 中的每个 node：
   - 沿前向 edges（这个 node 影响了什么）
   - 沿反向 edges（什么依赖这个 node）
3. 扩展到 `max_depth` 跳（默认：2）
4. 把所有到达的 nodes 收集为"impacted"

这同时捕获下游效应（调用变更代码的东西）和上游上下文（变更代码所依赖的东西）。
