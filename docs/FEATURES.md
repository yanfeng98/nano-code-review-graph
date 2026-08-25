# 功能

> 本 fork 不发布到 PyPI。下文是上游项目的历史功能记录，其中「PyPI 自动发布」「基于 `uvx` 的可移植配置」等条目不适用于本 fork（已移除 `publish.yml` 与 `uvx` 路径）。当前用法见 README：`uv sync --extra dev` / `uv run code-review-graph …`，或构建本地 wheel 分发。

## v2.3.7（当前）
- **无需 fork 的自定义语言**：在你的 repo 中放入 `.code-review-graph/languages.toml`，即可索引 tree-sitter-language-pack 提供的任何 grammar——扩展名映射加 node-type 列表，经过校验和上限控制，内置语言始终优先。参见 [CUSTOM_LANGUAGES.md](CUSTOM_LANGUAGES.md)。
- **docs/FAQ.md**：CRG 与 LSP、RAG、grep/agentic 搜索及相邻工具的对比；何时*不*该使用它；验证步骤；monorepo/worktree 与 registry 指引。
- **贡献脚手架**：GitHub issue forms（bug/feature/platform）、镜像 CONTRIBUTING checklist 的 PR 模板，以及 pip + GitHub Actions 的 dependabot 配置。
- **Windows 修复**：`daemon status` 不再以 WinError 87 崩溃（#511），CLI `detect-changes` 将 diff 路径映射为绝对原生路径，因此不再报告 0 个 functions（#528）。
- **Provider 名称校验**：未知的 embedding provider 名称会抛出清晰的错误并列出有效 providers，而不是静默回退到本地模型。
- **Store-leak 修复**：五个分析类 MCP tools 和 wiki-page tool 不再泄漏 SQLite 连接（try/finally `store.close()`）。
- **`fastmcp<4` 上限**：下一个 fastmcp 主版本不再可能静默破坏 server。
- **Worktree 安全的 git hooks**：`install` 通过 `git rev-parse --git-path hooks` 解析真实的 hooks 目录，因此链接的 worktrees 和 `core.hooksPath`（husky）环境也能获得可用的 pre-commit hook。

## v2.3.5
- **每个 brief CLI 调用上的 Token Savings 面板**：`code-review-graph detect-changes --brief` 和新增的 `code-review-graph update --brief` 打印带边框的 `Token Savings` 面板——全上下文 baseline、graph 响应、省下的 tokens、百分比，以及按类别细分（Functions / Tests / Risk / Other），其总和恰好等于 graph 响应大小。
- **`--verify` flag**：与 OpenAI 的 `cl100k_base` tokenizer（GPT-4 家族）交叉核对显示的数字。新增第二行 `Verified (tiktoken)`，显示真实 token 计数。跨 192 个混合语言文件的校准显示，该估算在整体上与真实 tokens 的误差在约 4% 以内。
- **`update --brief`**：增量更新 + 同一个 risk 面板，一个命令完成。与 `detect-changes --brief`（对现有 graph 只读）不同——当 graph 可能过期时（rebase 后、大变更集）使用 update。
- **`code-review-graph embed` CLI 子命令**：显式的 shell 级 embedding 生成入口。此前只能通过 MCP 触达。
- **更丰富的语义搜索**：`embeddings._node_to_text` 现在包含点分形式（`Module.Class.method`）、分词标识符和所在模块目录，显著提升自然语言查询的搜索排名。
- **标识符感知的搜索增强**：`extract_query_identifiers` 从 NL 查询中提取 dotted / snake_case / CamelCase tokens，并在 hybrid search 中把匹配的 qualified-names 权重提升 ×2.0。
- **Test-gap 去重**：brief 摘要中的 `Untested:` 行按裸名去重（针对重复 qualified_names 混入时的防御性保护）。

## v2.3.4
- **估算的 context savings**：Review、impact、detect-changes 和紧凑 architecture 响应包含微小的 `context_savings` 元数据（`estimated`、`saved_tokens`、`saved_percent`），适用于可以估算 baseline 的场景。
- **默认紧凑的 architecture overview**：`get_architecture_overview_tool` 默认 `detail_level="minimal"`，以避免庞大的成员列表和逐 edge 的 payload。需要完整细节时使用 `detail_level="standard"`。
- **受限的变更分析**：`CRG_MAX_CHANGED_FUNCS`、`CRG_MAX_TRANSITIVE_FRONTIER` 和 `CRG_TOOL_TIMEOUT` 帮助保持大型 MCP review 调用的响应性。
- **Windows MCP 可靠性**：本地 embedding 模型在 Windows 上会在 FastMCP 启动 worker dispatch 之前预热，以避免语义搜索死锁。
- **Parser 正确性**：Rust `#[test]` 和常见的 async test 属性现在会生成 `Test` nodes。
- **Graph 查找正确性**：Review、impact 和 file-summary tools 将用户可见路径解析为存储的 graph 路径；`callers_of` 即使存在同文件 callers 时也会包含跨文件 callers。
- **安装/运行时可靠性**：生成的 Codex/Claude hooks 会排空 stdin，wheel 中提供捆绑的文档，缺失的本地 embeddings 报告不可用状态。
- **CLI 可靠性**：`build --skip-postprocess` 和 `update --skip-flows` 遵守所请求的 post-processing 级别。
- **广泛的 parser 覆盖**：Python、JavaScript/TypeScript/TSX、Rust、C/C++、shell 脚本、Verilog/SystemVerilog、Ansible playbooks/roles/tasks、通过 TypeScript parser 解析的 Astro 文件，以及 Jupyter notebooks。通用 YAML 不被当作源码处理。
- **设计上的本地优先**：SQLite graph 存储保持本地，无遥测、无 cloud-default 行为。

## v2.0.0
- **22 个 MCP tools**（从 9 个增加到）：面向 flows、communities、architecture、refactoring、wiki、multi-repo 和 risk-scored 变更检测的 13 个新 tools。
- **5 个 MCP prompts**：`review_changes`、`architecture_map`、`debug_issue`、`onboard_developer`、`pre_merge_check` 工作流模板。
- **18 种语言**（从 15 种增加）：新增 Dart、R、Perl 支持。
- **Execution flows**：从入口点（HTTP handlers、CLI commands、tests）追踪调用链，按 criticality 分数排序。
- **Community detection**：通过 Leiden 算法（igraph）或基于文件的 grouping 聚类相关代码实体。
- **Architecture overview**：自动生成的 architecture 图，带模块摘要和跨 community coupling 警告。
- **Risk-scored 变更检测**：`detect_changes` 将 git diffs 映射到受影响的 functions、flows、communities 和测试覆盖缺口，并按优先级排序。
- **Refactoring tools**：带编辑列表的 rename preview、死代码检测、community 驱动的 refactoring 建议。
- **Wiki 生成**：为每个 community 自动生成 markdown wiki 页面，可选 LLM 摘要（ollama）。
- **Multi-repo registry**：注册多个 repositories，用 `cross_repo_search` 跨所有 repositories 搜索。
- **全文搜索**：带 porter stemming 的 FTS5 虚拟表，用于 hybrid keyword + vector 搜索。
- **自包含 schema**：`_SCHEMA_SQL` 一次性创建完整 schema（无版本化迁移；schema 变更需删除 `.code-review-graph/` 重建）。
- **可选依赖组**：`[embeddings]`、`[google-embeddings]`、`[communities]`、`[wiki]`、`[all]`。
- **TypeScript 路径解析**：tsconfig.json paths/baseUrl alias 解析用于 imports。
- **486 个 tests**，分布在 22 个 test 文件。

## v1.8.4
- **多词 AND 搜索**：`search_nodes` 现在要求所有词都匹配（大小写不敏感），产生更精确的结果。
- **Call target 解析**：裸 call targets 使用同文件定义解析为 qualified names，提高 `callers_of`/`callees_of` 准确度。
- **Impact radius 分页**：`get_impact_radius` 返回 `truncated` flag 和 `total_impacted` 计数；`max_results` 参数控制输出大小。
- **`find_large_functions_tool`**：新的 MCP tool，查找超过行数阈值的 functions、classes 或 files。
- **15 种语言**：新增 Vue SFC 和 Solidity 支持。
- **文档全面整改**：所有 docs 更新为准确的语言/工具计数、版本引用和 VS Code 扩展一致性。

## v1.8.3
- **Parser 递归保护**：`_MAX_AST_DEPTH = 180` 防止深层嵌套 AST 上的栈溢出。
- **模块缓存上限**：`_MODULE_CACHE_MAX = 15,000`，自动淘汰。
- **Embeddings 线程安全**：EmbeddingStore SQLite 上 `check_same_thread=False`。
- **Embeddings 重试逻辑**：Google Gemini API 调用的指数退避。
- **可视化 XSS 加固**：JSON 序列化中 `</` 转义为 `<\/`。
- **CLI 错误处理**：将宽泛的 `except` 拆分为具体的 handlers。
- **Git 超时**：可通过 `CRG_GIT_TIMEOUT` 环境变量配置。
- **治理文件**：CONTRIBUTING.md、SECURITY.md、CODE_OF_CONDUCT.md。

## v1.8.2
- **C# 解析修复**：语言标识符从 `c_sharp` 重命名为 `csharp`。
- **Watch 模式线程安全**：SQLite 连接与 Python 3.10/3.11 watchdog 线程兼容。
- **完整重建清理**：完整重建期间清除已删除文件的过期数据。
- **依赖精简**：移除未使用的 `gitpython` 依赖。

## v1.7.0
- **`install` 命令**：新的主要设置入口（`code-review-graph install`）。`init` 保留为 alias。
- **`--dry-run` flag**：预览 `install`/`init` 将要写入的内容而不修改文件。
- **PyPI 自动发布**：GitHub releases 现在自动发布到 PyPI。
- **README 重写**：用来自 httpx、FastAPI 和 Next.js 的真实 benchmark 数据编写专业文档。

## v1.6.4
- **可移植 MCP 配置**：`init` 现在生成基于 `uvx` 的 `.mcp.json`——无绝对路径，在装有 `uv` 的任何机器上都可用
- **移除 symlink 变通方案**：有了 `uvx` 后，不再需要处理路径中空格的 `_safe_path` 辅助函数

## v1.6.3
- **SessionStart hook**：Claude Code 在 session 启动时自动优先使用 graph MCP tools 而非整个 codebase 扫描
- **Marketplace ready**：plugin.json 已修正，用于官方 Claude Code plugin marketplace 提交
- **README 清理**：移除截图占位符

## v1.6.2
- **24 项审计修复**：关键 bug 修复、性能改进、parser 增强、测试覆盖扩大
- **Parser：C/C++ 支持**：对 C 和 C++ 的完整 node 提取（classes、functions、imports、calls、inheritance）
- **Parser：名称提取**：修复 Kotlin、Swift（simple_identifier）、Ruby（constant）
- **性能**：NetworkX graph 缓存、批量 edge 查询、分块 embedding 搜索、git subprocess 超时
- **CI 加固**：覆盖率强制执行（50%）、bandit 安全扫描、mypy 类型检查
- **Tests**：为增量更新、embeddings 和 7 个新语言 fixtures 新增 +40 个 tests
- **Docs**：API 响应 schema、ignore pattern 文档、修复 hook 配置参考
- **无障碍**：整个 D3.js 可视化中加入 ARIA labels

## v1.5.3
- **路径中含空格处理**：*（在 v1.6.4 中被基于 `uvx` 的配置取代）* 之前使用 symlinks 处理路径中的空格
- **无需 git**：`build`、`status`、`visualize`、`watch` 现在可在任何目录下工作，无需 git
- **Plugin ready**：Skills 注册到 plugin.json，SKILL.md frontmatter 已修正
- **文件组织**：生成的文件移入 `.code-review-graph/` 目录（自动创建 `.gitignore`，旧版迁移）
- **可视化密度**：初始折叠（仅 File nodes）、搜索栏、可点击的 edge 类型开关、面向大型 graph 的 scale-aware 布局
- **项目清理**：移除冗余的 `references/`、`agents/`、`settings.json`

## v1.4.0
- **`init` 命令**：自动为 Claude Code 集成设置 `.mcp.json`
- **交互式 D3.js graph 可视化**：`code-review-graph visualize` 生成可在浏览器中探索的 HTML graph
- **文档全面整改**：跨所有参考文件进行全面的 docs 审计

## v1.3.0
- **Python 版本检查 + Docker 回退**：自动检测 Python 3.10+，不可用时建议 Docker
- **通用安装**：`pip install code-review-graph`——无需 git clone
- **CLI 入口点**：pip 安装后 `code-review-graph` 命令在系统范围内可用

## v1.2.0
- **日志改进**：整个 codebase 中的结构化日志
- **Watch 防抖**：watch 模式中更智能的文件变更检测
- **tools.py 修复**：MCP tools 的 bug 修复与可靠性改进
- **CI 覆盖率**：带测试覆盖率报告的 GitHub Actions CI/CD pipeline

## v1.1.0
- **Watch 模式**：`code-review-graph watch`——文件变更时自动重建 graph
- **向量 embeddings**：可选的 `pip install .[embeddings]`，用于语义代码搜索
- **Rust 已验证**：12+ 种语言，带专门的测试覆盖
- **47 个 tests 通过**，注册了 8 个 MCP tools
- README badges 和更清晰的安装流程

## v1.0.0（基础）
- **持久化 SQLite 知识图谱**——零外部依赖
- **Tree-sitter 多语言解析**——classes、functions、imports、calls、inheritance
- **增量更新**，通过 `git diff` + 自动依赖级联
- **Impact-radius / blast-radius 分析**——通过 call/import/inheritance graph 的 BFS
- **6 个 MCP tools**，用于完整的 graph 交互
- **4 个 skills**：explore-codebase、review-changes、debug-issue、refactor-safely
- **PostToolUse hooks**（Write|Edit|Bash），用于自动后台更新
- **FastMCP 3.0 兼容**的 stdio MCP server

## 隐私与数据
- 核心 graph 数据存储在本地
- Graph 存储在 `.code-review-graph/graph.db`（SQLite），自动 gitignored
- 无遥测；核心 graph/review 工作流不需要网络访问
- 可选的 embedding 和 wiki 功能在显式启用时可能调用已配置的本地或远程服务
- 遵守 `.gitignore` 和 `.code-review-graphignore`
