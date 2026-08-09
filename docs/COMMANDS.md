# 所有可用命令

## Skills 与斜杠命令

以下 4 个 skills 为支持项目 skills 或斜杠命令风格工作流的 clients 安装（写入 `.claude/skills/`）。

### `/explore-codebase`
用知识图谱导航和理解 codebase 结构。

### `/review-changes`
用变更检测和 impact 分析做结构化 code review。
- 通过 git diff 自动检测变更的文件
- 计算 blast radius（默认 2 跳）
- 生成带指导的结构化 review

### `/debug-issue`
用 graph 驱动的代码导航系统化调试问题。

### `/refactor-safely`
用依赖分析安全地规划与执行重构。

> 命名约定：skills 是 `.claude/skills/` 里的本地文件，在 Claude Code 中显示为 `/skill-name`（无前缀）；MCP prompts 显示为 `/code-review-graph:prompt_name`（下划线命名，带 server 前缀）。两者都需先运行 `code-review-graph install` 才会出现。
> 构建 graph 不是 skill 也不是 prompt，而是 MCP tool `build_or_update_graph_tool`（见下）或 CLI `code-review-graph build` / `update`。
> 现成的 review 工作流通过 MCP prompts 提供：`review_changes`（审查变更）、`pre_merge_check`（审查 PR，见下）。

## MCP Tools

### 核心 Tools

#### `build_or_update_graph_tool`
```
full_rebuild: bool = False           # True 表示完整重新解析
repo_root: str | None                # 自动检测
base: str | None = None              # Diff base；None 时自动解析为上次同步的 commit
postprocess: str = "full"            # "full"、"minimal" 或 "none"
recurse_submodules: bool | None      # 回退到 CRG_RECURSE_SUBMODULES
```

#### `run_postprocess_tool`
```
flows: bool = True
communities: bool = True
fts: bool = True
repo_root: str | None
```

#### `get_minimal_context_tool`
```
task: str = ""                       # 你正在做什么
changed_files: list[str] | None      # 省略时从 VCS 自动检测
repo_root: str | None
base: str = "HEAD~1"
```

#### `get_impact_radius_tool`
```
changed_files: list[str] | None  # 从 VCS 自动检测
max_depth: int = 2               # graph 中的跳数
repo_root: str | None
base: str = "HEAD~1"
detail_level: str = "standard"   # "standard" 或 "minimal"
```
相关响应可能包含紧凑的估算 `context_savings` 元数据。

#### `query_graph_tool`
```
pattern: str    # callers_of, references_to, callees_of, imports_of, importers_of,
                # children_of, tests_for, inheritors_of, triggers_of, triggered_by,
                # publishers_of, listeners_of, handlers_of, endpoints_for, file_summary
target: str     # Node 名称、qualified name 或文件路径
repo_root: str | None
detail_level: str = "standard"   # "standard" 或 "minimal"
```

#### `get_review_context_tool`
```
changed_files: list[str] | None
max_depth: int = 2
include_source: bool = True
max_lines_per_file: int = 200
repo_root: str | None
base: str = "HEAD~1"
detail_level: str = "standard"   # "standard" 或 "minimal"
```
相关响应可能包含紧凑的估算 `context_savings` 元数据。

#### `traverse_graph_tool`
```
query: str
depth: int = 3                  # 1-6
mode: str = "bfs"               # "bfs" 或 "dfs"
token_budget: int = 2000
repo_root: str | None
```

#### `semantic_search_nodes_tool`
```
query: str           # 搜索字符串
kind: str | None     # File、Class、Function、Type、Test
limit: int = 20
repo_root: str | None
model: str | None    # Embedding 模型（回退到 provider 相关的环境变量）
provider: str | None # local、openai
detail_level: str = "standard"
```

#### `embed_graph_tool`
```
repo_root: str | None
model: str | None    # Embedding 模型名称
provider: str | None # local、openai
```
本地 embeddings 需要：`pip install "code-review-graph[embeddings]"`。Cloud providers 使用 stdlib HTTP clients，需要它们各自的 provider 环境变量。

#### `list_graph_stats_tool`
```
repo_root: str | None
```

#### `find_large_functions_tool`
```
min_lines: int = 50                # 最小行数阈值
kind: str | None                   # File、Class、Function 或 Test
file_path_pattern: str | None      # 按文件路径子串过滤
limit: int = 50                    # 返回的最大结果数
repo_root: str | None
```

#### `get_docs_section_tool`
```
section_name: str    # usage, review-delta, review-pr, commands, legal, watch, embeddings, languages, troubleshooting
```

### Flow Tools

#### `list_flows_tool`
```
sort_by: str = "criticality"  # criticality, depth, node_count, file_count, name
limit: int = 50
kind: str | None              # 按入口点类型过滤（例如 "Test"、"Function"）
repo_root: str | None
detail_level: str = "standard"
```

#### `get_flow_tool`
```
flow_id: int | None          # 来自 list_flows_tool 的 Database ID
flow_name: str | None        # 要搜索的名称（部分匹配）
include_source: bool = False # 为每一步包含 source snippets
repo_root: str | None
```

#### `get_affected_flows_tool`
```
changed_files: list[str] | None  # 从 VCS 自动检测
base: str = "HEAD~1"
repo_root: str | None
```

### Community Tools

#### `list_communities_tool`
```
sort_by: str = "size"    # size, cohesion, name
min_size: int = 0
repo_root: str | None
detail_level: str = "standard"
```

#### `get_community_tool`
```
community_name: str | None   # 要搜索的名称（部分匹配）
community_id: int | None     # Database ID
include_members: bool = False
repo_root: str | None
```

#### `get_architecture_overview_tool`
```
repo_root: str | None
detail_level: str = "minimal"    # "minimal" 紧凑默认， "standard" 完整细节
```
Minimal 响应可能包含紧凑的估算 `context_savings` 元数据。

### Graph Health 与 Architecture Tools

#### `get_hub_nodes_tool`
```
top_n: int = 10
repo_root: str | None
```

#### `get_bridge_nodes_tool`
```
top_n: int = 10
repo_root: str | None
```

#### `get_knowledge_gaps_tool`
```
repo_root: str | None
```

#### `get_surprising_connections_tool`
```
top_n: int = 15
repo_root: str | None
```

#### `get_suggested_questions_tool`
```
repo_root: str | None
```

### 变更分析与 Refactoring Tools

#### `detect_changes_tool`
```
base: str = "HEAD~1"
changed_files: list[str] | None
include_source: bool = False
max_depth: int = 2
repo_root: str | None
detail_level: str = "standard"
```
代码 review 的主要 tool。将变更的文件映射到受影响的 functions、flows、communities 和测试覆盖缺口。返回 risk scores 和按优先级排序的 review 条目。
相关响应可能包含紧凑的估算 `context_savings` 元数据。

#### `refactor_tool`
```
mode: str = "rename"         # "rename"、"dead_code" 或 "suggest"
old_name: str | None         # (rename) 当前 symbol 名称
new_name: str | None         # (rename) 新名称
kind: str | None             # (dead_code) Function 或 Class
file_pattern: str | None     # (dead_code) 按文件路径子串过滤
repo_root: str | None
```

#### `apply_refactor_tool`
```
refactor_id: str             # 来自先前 refactor_tool 调用的 ID
repo_root: str | None
dry_run: bool = False        # 返回 diff 而不写入文件
```

### Wiki Tools

#### `generate_wiki_tool`
```
repo_root: str | None
force: bool = False          # 即使未变更也重新生成所有页面
```

#### `get_wiki_page_tool`
```
community_name: str          # 要查找的 community 名称
repo_root: str | None
```

### Multi-Repo Tools

#### `list_repos_tool`
```
(无参数)
```

#### `cross_repo_search_tool`
```
query: str
kind: str | None
limit: int = 20
```

## MCP Prompts（5 个工作流模板）

### `review_changes`
使用 detect_changes、affected_flows 和测试缺口的提交前 review 工作流。
```
base: str = "HEAD~1"
```

### `architecture_map`
使用 communities、flows 和 Mermaid diagrams 的 architecture 文档。

### `debug_issue`
使用搜索、flow 追踪和最近变更的引导式调试。
```
description: str = ""
```

### `onboard_developer`
使用 stats、architecture 和关键 flows 的新开发者入职引导。

### `pre_merge_check`
带 risk scoring、测试缺口和死代码检测的 PR 就绪检查。
```
base: str = "HEAD~1"
```

## CLI Commands

```bash
# 设置
code-review-graph install           # 配置检测到的 AI 编码 platforms（alias：init）
code-review-graph install --dry-run # 预览而不写入文件
code-review-graph install --platform codex  # 配置一个 platform
code-review-graph uninstall                 # 移除所有 CRG 配置、hooks、skills 和数据
code-review-graph uninstall --platform codex  # 解绑一个 platform（保留 graph 数据与其他 platform）
code-review-graph enrich                    # 用 graph 上下文增强 hook 输入（PreToolUse hook；从 stdin 读取一个 JSON 对象）

# Build 与 update
code-review-graph build                        # 完整 build
code-review-graph build --skip-flows           # 仅解析 + signatures + FTS
code-review-graph build --skip-postprocess     # 仅原始解析
code-review-graph update                       # 增量更新
code-review-graph update --base origin/main    # 自定义 base ref
code-review-graph update --brief               # 更新 graph + 显示 risk 面板
code-review-graph update --brief --verify      # ……并与 tiktoken 交叉核对
code-review-graph postprocess                  # 重新运行 flows、communities、FTS
code-review-graph forget PATH [PATH ...]       # 从 graph 中丢弃已解析的文件（无需完整重建）
code-review-graph forget src/legacy --dry-run  # 预览哪些文件会被遗忘
code-review-graph embed --provider local       # 为语义搜索计算 vector embeddings
code-review-graph update --embedding-provider local --embedding-model all-MiniLM-L6-v2
                                                # 显式刷新现有索引（默认：关闭）

# 监控与检查
code-review-graph status                       # Graph 统计
code-review-graph watch                        # 文件变更时自动更新
code-review-graph visualize                    # 生成交互式 HTML graph
code-review-graph visualize --format graphml   # 导出 GraphML
code-review-graph visualize --serve            # 在 localhost:8765 上提供 graph.html

# 分析
code-review-graph detect-changes               # Risk-scored 变更分析
code-review-graph detect-changes --base HEAD~3 # 自定义 base ref
code-review-graph detect-changes --brief       # 带 token-savings 估算的紧凑面板
code-review-graph detect-changes --brief --verify  # ……并与 tiktoken 交叉核对
code-review-graph detect-changes --churn       # 添加 opt-in 的变更频率风险

# detect-changes 与 update --brief 的选择？
# • detect-changes --brief：只读。回答"我当前的变更对现有 graph 的影响是什么？"
#   快速（约 1s）。在 graph 已是最新时使用（若安装了 hooks，则这是默认情况）。
# • update --brief：先把变更的文件重新解析进 graph，然后运行同样的分析。
#   在 rebase 之后、大变更集之后，或任何你怀疑 graph 过期时使用。
# 两者都以相同的 "Token Savings" 面板结束。

# Graph 检查（MCP tools 的 CLI 镜像）
code-review-graph query callers_of <target>       # 查询 graph 关系（patterns：callers_of, callees_of,
                                                  #   imports_of, importers_of, children_of, tests_for,
                                                  #   inheritors_of, file_summary）
code-review-graph impact --files src/a.py src/b.py  # 分析变更的 blast radius
code-review-graph search "parse_file"               # 搜索 graph 实体
code-review-graph flows                              # 列出存储的 execution flows
code-review-graph flow --name "login flow"           # 显示一个 flow（--id 或 --name）
code-review-graph communities                        # 列出 graph communities
code-review-graph community --id 3                   # 显示一个 community（--id 或 --name）
code-review-graph architecture                       # 显示 architecture overview
code-review-graph large-functions                    # 查找过大的 graph nodes
code-review-graph dead-code                          # 查找无 callers 或 test 引用的 functions/classes
code-review-graph refactor rename --old-name foo --new-name bar  # 预览 graph 支持的 refactor

# Wiki
code-review-graph wiki                         # 从 communities 生成 markdown wiki

# Multi-repo
code-review-graph register <path> [--alias name]  # 注册一个 repository
code-review-graph unregister <path_or_alias>       # 从 registry 移除
code-review-graph repos                            # 列出已注册的 repositories

# Daemon（multi-repo watcher）——随 install 附带，无额外依赖
code-review-graph daemon start [--foreground]       # 启动 watch daemon
code-review-graph daemon stop                       # 停止 daemon
code-review-graph daemon restart [--foreground]     # 重启 daemon
code-review-graph daemon status                     # 显示 daemon 状态与 repos
code-review-graph daemon logs [--repo ALIAS] [--follow]  # 查看 daemon 或单 repo 日志
code-review-graph daemon add <path> [--alias NAME]  # 向 daemon 配置添加 repo
code-review-graph daemon remove <path_or_alias>     # 从 daemon 配置移除 repo

# Server
code-review-graph serve                        # 启动 MCP server（stdio）
code-review-graph serve --http                 # localhost:5555 上的 Streamable HTTP
code-review-graph serve --tools query_graph_tool,detect_changes_tool  # Tool 白名单
code-review-graph mcp                          # serve 的 alias
```

## 独立 Daemon CLI（`crg-daemon`）

`crg-daemon` 命令随每次 `code-review-graph` 安装附带——无需单独安装。它也可作为独立入口点使用。它镜像 `code-review-graph daemon` 的子命令：

```bash
crg-daemon start [--foreground]       # 启动 multi-repo watch daemon
crg-daemon stop                       # 停止 daemon 和所有 watcher 进程
crg-daemon restart [--foreground]     # 重启（stop + start）
crg-daemon status                     # 显示 daemon 状态、repos 和进程存活情况
crg-daemon logs [--repo ALIAS] [-f] [-n N]  # 追踪 daemon 或单 repo 日志文件
crg-daemon add <path> [--alias NAME]  # 向 watch.toml 添加 repository
crg-daemon remove <path_or_alias>     # 从 watch.toml 移除 repository
```

### 配置

Daemon 从 `~/.code-review-graph/watch.toml` 读取配置：

```toml
session_name = "crg-watch"   # 逻辑 daemon 名称
log_dir = "~/.code-review-graph/logs"
poll_interval = 2            # 配置文件轮询间隔（秒）

[[repos]]
path = "/home/user/project-a"
alias = "project-a"

[[repos]]
path = "/home/user/project-b"
alias = "project-b"
```

Daemon 为每个 repo 生成一个 `code-review-graph watch` 子进程，通过 `subprocess.Popen` 管理。它监控配置文件的变化，并自动协调子进程（随 repos 的添加或移除而启动/停止）。健康检查每 30 秒运行一次，自动重启死亡的 watchers。无外部依赖（tmux、screen 等）。
