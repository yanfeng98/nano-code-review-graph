# FAQ — code-review-graph 的对比

对我们最常被问到的问题的诚实回答。如果某个任务确实有别的工具做得更好，本页会直说。

- [与 LSP 和 language servers 有何不同？](#与-lsp-和-language-servers-有何不同)
- [这不就是 RAG 吗？](#这不就是-rag-吗)
- [为什么不用 grep？](#为什么不用-grep)
- [与 Serena、codegraph、claude-context 和 repomix 相比如何？](#与-serena-codegraph-claude-context-和-repomix-相比如何)
- [何时不应使用它？](#何时不应使用它)
- [它会回传数据吗？](#它会回传数据吗)
- [如何验证它正常工作？](#如何验证它正常工作)
- [多大的 codebase 才值得使用它？](#多大的-codebase-才值得使用它)
- [如何处理 monorepos、git worktrees 和多个 repos？](#如何处理-monorepos-git-worktrees-和多个-repos)

---

## 与 LSP 和 language servers 有何不同？

Language servers 和 code-review-graph（CRG）都会为你的代码构建结构性模型，但它们优化的目标不同。

**LSP 做得更好的地方。** language server 由真正的编译器前端（或接近它的东西）支撑，因此能给你类型感知、语义精确的结果：穿过 generics 和 overloads 的精确 go-to-definition、理解 scoping 的 find-references、实时 diagnostics、completions，以及结构上保证安全的 renames。如果你需要某个语言中某个 symbol 的*可证明完整*的引用列表，LSP server 是黄金标准，CRG 并不试图取代它。

**CRG 的不同之处：**

- **一个持久化的 graph，而非每种语言一个 daemon。** Language servers 每种语言运行一个进程，并且（除了少数在磁盘上缓存索引的例外）会在每次 session 重建或重新校验状态。CRG 用 Tree-sitter 解析一次，将 nodes 和 edges 存储在单个 SQLite 文件（`.code-review-graph/graph.db`）中，并从单一进程在约 13 种内置语言外加 notebooks 上回答查询——包括没有任何单个 LSP server 建模的 cross-language edges。
- **它跨越 sessions 和 commits 持续存在。** graph 采用增量更新（仅变更的文件，在约 2,900 个文件的 repo 上不到 2 秒），而非每次 editor session 都重建。
- **面向 review 的 edges。** `tests_for`、execution flows、community membership、risk-scored 的变更分析——这些关系 LSP 不建模，因为编辑时并不需要它们。

**诚实的权衡：** CRG 的 call 解析是 AST 级别且启发式的，并非由编译器支撑。Dynamic dispatch、metaprogramming 和 duck typing 可能产生推断或模糊的 edges——这正是每条 edge 都带有 confidence tier（`EXTRACTED` / `INFERRED` / `AMBIGUOUS`）的原因。LSP 对单个 symbol 更精确；CRG 更广、更持久，并且在整个 repo 上查询更便宜。

## 这不就是 RAG 吗？

不是。RAG 把你的代码切成文本 chunks，对它们做 embedding，然后按与查询的相似度检索 chunks。它能回答"找到*提到* X 的代码"，却无法回答"谁*调用* X"——两个函数之间的相似度说明不了其中一个是否会调用另一个。

CRG 存储的是**从 AST 解析出的结构性 edges**：calls、imports、inheritance、测试覆盖。"谁调用 `login()`"是一次 graph 查找，而不是相似度猜测。Embeddings 在 CRG 中确实存在，但它们是可选的，扮演辅助角色——作为 hybrid search（FTS5 BM25 keyword + vector）的一种输入，用于找到*起始 node*，之后 traversal 沿真实 edges 进行。目前只对函数签名做 embedding（每个 node 约 10 tokens），不包括函数体。

最能体现差异的场景是多跳检索：自然语言查询 → anchor node → 一跳 traversal（`callers_of`、`tests_for`……）。纯相似度检索没有对应的第二跳。

**RAG 式搜索更好的地方：** 针对散文、注释和文档的纯概念性问题（"哪里讨论了 rate limiting？"）。CRG 自身的关键词搜索排名是一个已记录的弱点。

## 为什么不用 grep？

问得好——Anthropic 已经明确表示 Claude Code 刻意*不带*代码索引发布。Agentic 搜索（glob、grep、定向文件读取）总是与你的工作区一样新鲜，没有 chunking 或过期的失败模式，且零配置。对于单跳问题——"`parse_file` 定义在哪里？"——这种方式效果很好，CRG 不会比它好太多。

差距出现在**多跳结构性问题上**，每一跳都会让 agent 多花一轮 grep + read + 推理，token 开销会累积：

- **Impact radius**——"如果我改动这个文件，什么可能被破坏？"需要 callers、dependents *以及*它们的 tests。一次 `get_impact_radius` 调用即可返回全部三类。
- **Callers of callers**——通过 `traverse_graph` 或重复的 `query_graph(pattern="callers_of")` 进行传递追踪，而非为每个中间名做 N 轮 grep（而且 grep 匹配的是*文本*，所以重载或 re-export 的名字会产生 agent 必须读取才能排除的误报）。
- **Tests for**——`query_graph(pattern="tests_for")` 通过解析出的 edges 加命名约定，把代码映射到覆盖它的 tests；`detect_changes` 再补充传递性的测试覆盖。Grep 只能找到字面提到该名字的 tests。
- **Affected flows**——"这次变更触及哪些执行路径？"完全没有 grep 等价物。

graph 还是持久化的：agentic 搜索每次 session 都从头重新推导同样的结构，而 CRG 把它放在 SQLite 中并增量更新。

对于小型 repo 中的单跳查找，grep 便宜又好用；多跳的 review 工作流才是 graph 真正体现价值之处。

## 与 Serena、codegraph、claude-context 和 repomix 相比如何？

这些都是解决相邻问题的好工具。基于各项目公开文档的简短事实对比（当前行为请查阅上游文档）：

| Tool | 方法 | 持久化 | 外部依赖 | 审查重点 |
|---|---|---|---|---|
| **code-review-graph** | Tree-sitter AST → 结构性 graph（calls、imports、inheritance、tests），通过 MCP + CLI | SQLite 位于 `.code-review-graph/`，增量更新 | 核心无依赖；embeddings 可选 | 是 —— blast radius、risk-scored 变更分析、test-gap 检测 |
| **Serena** | 基于 LSP 的 symbol 检索与编辑工具，通过 MCP | Language-server 状态 + 按项目 memories | 每种语言一个 language server | 通用编码 agent 工具包，非审查专用 |
| **codegraph** | 基于 MCP 的 AST/call-graph 索引（多个项目共用此名；细节因实现而异） | 因实现而异 | 因实现而异 | 通常以检索为主 |
| **claude-context** | 基于 MCP 的 chunk + embed 语义代码搜索 | 向量数据库中的 vector index | Embedding provider + vector DB（云端或自托管） | 以搜索为主，非审查专用 |
| **repomix** | 将整个 repo 打包成一个 AI 友好文件 | 无 —— 每次运行重新生成 | Node.js | 一次性 context 打包；无结构性查询 |

大致建议：如果你想要 symbol 精确的*编辑*工具，Serena 的 LSP 方式更合适。如果你想要语义*搜索*，并且愿意运行一个 vector store，claude-context 覆盖了这一点。如果你的 repo 小到足以整体粘贴进一个大的 context window，repomix 是最简单的可行方案。CRG 的定位是用于**审查**的持久化结构性 graph：影响分析、risk scoring 和测试覆盖追踪，且无外部服务。

## 何时不应使用它？

结合已记录的开销权衡：

- **几百个文件以下的 repos。** Agent 通常可以直接读取所有相关内容；graph 的结构性元数据会带来小型 repo 不值得付出的开销。参见 [多大的 codebase 才值得使用它？](#多大的-codebase-才值得使用它)
- **琐碎的单文件变更。** Graph 响应携带 impact-radius edges 和源码片段，可能超过一个单文件 diff 的原始内容。
- **对不会再回访的 repo 的一次性问题。** 构建很快（500 个文件的项目约 10 秒），但回报来自跨查询和跨 sessions 的*复用*。对于单个问题，agentic 搜索就足够了。
- **JS 上的 flow 检测。** 入口点检测目前主要对 Python 框架模式可靠；JavaScript 的 flow 检测有待改进。

## 它会回传数据吗？

不会。零遥测。Graph 是 repo 内 `.code-review-graph/` 中的一个 SQLite 文件，核心的 build / review / search / MCP 工作流完全在本地运行。Streamable-HTTP 的 MCP transport 默认绑定到 localhost。

唯一的网络活动是 opt-in：

- **本地 embeddings**（`pip install "code-review-graph[embeddings]"`）首次使用时从 HuggingFace 下载 sentence-transformers 模型。你的代码不会离开本机。
- **Cloud embeddings**（OpenAI 兼容）会把正在 embedding 的文本——目前是函数签名——发送给你通过环境变量显式配置的 provider。除非你用 `CRG_ACCEPT_CLOUD_EMBEDDINGS=1` 确认，CRG 会打印出 egress 警告；当端点是 localhost 时，该警告会自动跳过。

完整隐私说明参见 [LEGAL.md](LEGAL.md)。

## 如何验证它正常工作？

1. **检查 graph 存在且有内容：**

   ```bash
   code-review-graph status
   ```

   你应该看到 node/edge 计数和 graph 统计。零 nodes 意味着 build 没有运行，或没有找到可解析的内容。

2. **在真实变更上查看节省量**——做任意编辑，然后：

   ```bash
   code-review-graph detect-changes --brief
   ```

   这会基于现有 graph 打印 risk 摘要和带边框的 **Token Savings** 面板（只读）。添加 `--verify` 可与 OpenAI 的 `cl100k_base` tokenizer 交叉核对估算值（需要 `pip install tiktoken`）。如果你怀疑 graph 过期，`code-review-graph update --brief` 会先重新解析变更的文件，然后打印同样的面板。

3. **检查 MCP 接线**——在 Claude Code 中运行 `/mcp`，确认 `code-review-graph` server 已连接并列出其 tools。然后问 assistant 一个结构性问题（"什么调用了 `parse_file`？"），观察它使用 `query_graph` 而不是 grep。

如果其中任何一步失败，参见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

## 多大的 codebase 才值得使用它？

这个问题经常出现（参见 #414）。诚实建议，与已记录的小型 repo 开销相关联：

- **低于几百个文件：** 收益有限。Graph 几秒内构建完成且工作正常，但 agent 通常已经能在 context 中容纳大部分 repo，而且对于琐碎 diffs，结构性响应消耗的 token 可能比省下的还多（已记录的开销区间——参见 [何时不应使用它？](#何时不应使用它)）。
- **几百到几千个文件：** 结构化 graph 的构建和查询在这里回报显著——每个问题只需 graph 查询而非通读语料库。
- **数千文件级 repos 和 monorepos：** 最强的论据。没有 agent 能每个问题都通读语料库（单是 FastAPI 就有约 95 万 token 的源码），每次 session 都靠搜索重新推导结构是主要成本，而增量更新能在 2 秒内保持 graph 新鲜。

另一个轴与文件数同等重要：**你多久问一次多文件问题**。每天审查的 300 文件 repo，比一次性的 3,000 文件 repo 收益更大。

## 如何处理 monorepos、git worktrees 和多个 repos？

**Monorepos。** 默认每个 repository root 一个 graph——命令通过向上走到最近的 `.git` 自动检测 root，且 git repos 中只索引已跟踪的文件（`git ls-files`），所以 gitignored 的构建产物会被自动跳过。使用 `.code-review-graphignore` 文件排除已跟踪的路径（例如 `vendor/**`、生成的代码），或传 `--repo <path>` 让某个命令指向特定目录。

**Git worktrees。** 每个 worktree 被检测为独立的 root，所以各自有自己的 `.code-review-graph/` 数据库，与其 checkout 对应。不要试图让不同 commit 的 worktrees 共享一个数据库——graph 反映的是某一个 working tree。如果你想完全把数据库放在 working tree 之外（临时 workspace、网络共享），在 `build`/`update` 等命令上使用 `--data-dir <path>`，或设置 `CRG_DATA_DIR` 环境变量。

**多个 repos。** 一个轻量级 registry（存储在 `~/.code-review-graph/registry.json`）让 MCP clients 可以跨项目搜索：

```bash
code-review-graph register ~/work/api --alias api   # 添加 repo（可选 alias）
code-review-graph repos                             # 列出已注册的 repos
code-review-graph unregister api                    # 按路径或 alias 移除
```

注册后，`list_repos_tool` 和 `cross_repo_search_tool` 这两个 MCP tools 可以跨所有 repos 工作。要让多个 graphs 自动保持新鲜，内置 daemon 会把已注册的 repos 作为子进程监控：

```bash
crg-daemon add ~/work/api --alias api
crg-daemon start
crg-daemon status
```

（也可用 `code-review-graph daemon start|stop|status`。）完整的 daemon 参考参见 [COMMANDS.md](COMMANDS.md)。
