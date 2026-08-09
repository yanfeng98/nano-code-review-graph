# 路线图

## 已发布

### v2.3.7
- **无需 fork 的自定义语言**：`.code-review-graph/languages.toml` 把扩展名和 node types 映射到任意 tree-sitter-language-pack grammar（`docs/CUSTOM_LANGUAGES.md`）
- **`docs/FAQ.md`**：与 LSP、RAG、grep/agentic 搜索及相邻工具的对比，外加何时不应使用的指导
- **贡献脚手架**：issue forms、PR 模板、dependabot 配置
- **Windows 修复**：针对 `daemon status`（#511）和 `detect-changes` 路径映射（#528）
- **可靠性**：embedding provider-name 校验、analysis/wiki tools 中的 SQLite store-leak 修复、`fastmcp<4` 上限、通过 `git rev-parse --git-path hooks` 安装 hooks

### v2.3.5
- **`detect-changes --brief` 和新增的 `update --brief` 上的 Token Savings 面板**——带边框的 CLI 输出，含按类别细分，总和恰好等于 graph 响应大小
- **`--verify` flag** 对照 OpenAI 的 `cl100k_base` tokenizer 交叉核对显示的节省量；校准数据显示，该估算在整体上与真实 GPT-4 tokens 的偏差约在 4% 以内
- **`code-review-graph embed`** CLI 子命令，用于显式 embedding 生成
- **更丰富的 embedding 文本**和**标识符感知的搜索增强**提升了语义搜索准确度
- **brief 摘要中的 test-gap 去重**
- Demo GIF（`diagrams/context-savings-demo.gif`）展示两个 CLI 界面和 `--verify`

### v2.3.4
- 30 个 MCP tools 和 5 个 MCP prompts
- 为 review、impact、detect-changes 和紧凑 architecture 响应提供的估算 context savings 元数据
- 默认紧凑的 architecture overview，以减少大型 MCP payloads
- 面向大型 diffs 的受限变更分析控制（`CRG_MAX_CHANGED_FUNCS`、`CRG_MAX_TRANSITIVE_FRONTIER`、`CRG_TOOL_TIMEOUT`）
- Windows FastMCP 语义搜索死锁缓解
- Rust test 检测和路径查找正确性修复
- 为 2.3.4 发布刷新的文档和发布元数据

### v2.3.3
- 跨源语言、shell 脚本、notebooks 和 SFC 风格文件的广泛 parser 覆盖扩展
- 额外 AI 编码 platform 安装目标，包括 Gemini CLI、Qwen、Kiro、Qoder 和 GitHub Copilot 变体
- localhost 上的 Streamable HTTP MCP transport
- Parser/resolver、Windows、FastMCP 和 daemon 可靠性修复
- Community PR 扫描和 VS Code 无障碍改进

### v2.2.0
- Multi-repo watch daemon（`crg-daemon` / `code-review-graph daemon`）
- 基于 TOML 的 daemon 配置（`~/.code-review-graph/watch.toml`）
- 子进程管理：每个 repo 一个 `code-review-graph watch` 进程
- 配置文件监听，带 watcher 进程的自动协调
- 带 PID 文件管理的 daemonization
- 带死亡 watcher 自动重启的健康检查
- 独立 `crg-daemon` CLI 入口点（7 个子命令）
- 主 CLI 中集成的 `daemon` 子命令组

### v2.0.0
- 22 个 MCP tools（从 9 个增加到）和 5 个 MCP prompts
- 18 种语言（新增 Dart、R、Perl）
- 带 criticality 评分的执行流检测
- Community detection（通过 igraph 的 Leiden 算法，基于文件的回退）
- 带 coupling 警告的 architecture overview
- Risk-scored 变更检测（`detect_changes`）
- Refactoring tools（rename preview、死代码、建议）
- 从 community 结构生成 wiki
- 带跨 repo 搜索的 multi-repo registry
- 带 porter stemming 的 FTS5 全文搜索
- 数据库迁移（v1-v5）
- TypeScript tsconfig 路径 alias 解析
- MiniMax embedding provider（embo-01）
- 可选依赖组：`[embeddings]`、`[google-embeddings]`、`[communities]`、`[wiki]`、`[all]`
- 486 个 tests，分布在 22 个 test 文件

### v1.8.4
- 多词 AND 搜索、call target 解析、impact radius 分页
- `find_large_functions_tool`、Vue SFC 和 Solidity 支持
- 文档全面整改

### v1.7.0
- `install` 命令作为主要入口点（`init` 保留为 alias）
- `--dry-run` flag，用于预览 install/init 变更
- 发布时通过 GitHub Actions 自动发布到 PyPI
- README 重写，使用来自 httpx、FastAPI 和 Next.js 的真实 benchmark 数据

### v1.6.x
- 可移植的基于 `uvx` 的 MCP 配置
- 自动 graph 工具偏好的 SessionStart hook
- 24 项审计修复：C/C++ 支持、性能、CI 加固

### v1.5.x
- 生成的文件位于 `.code-review-graph/` 目录
- 可视化密度：折叠起始、搜索、edge 开关
- 无需 git 即可工作

### v1.4.0
- `init` 命令、交互式 D3.js 可视化、`serve` 命令

### v1.3.0
- 通用 pip 安装、CLI 入口点、Python 版本检查

### v1.1.0-v1.2.0
- Watch 模式、向量 embeddings、日志、CI 覆盖

### v1.0.0（基础）
- 持久化 SQLite 知识图谱、Tree-sitter 解析、增量更新
- Impact radius 分析、6 个 MCP tools、3 个 skills

## 计划中

- Team sync（通过 git 跟踪的 DB 共享 graph）
- 面向 monorepos（>50k 文件）的性能优化

## 进行中

- 按需添加语言 grammars
- 随 AI 编码 platform 演进进行集成更新
