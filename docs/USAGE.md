# Code Review Graph — 用户指南

**适用于：** v2.3.7

## 安装

```bash
pip install code-review-graph
code-review-graph install    # 自动检测并配置所有受支持的 platform
code-review-graph build      # 解析你的 codebase
```

`install` 会检测你已安装的 AI 编码工具，为每个工具写入正确的 MCP 配置，并在支持的地方安装 platform 原生的 hooks。安装后请重启你的编辑器/工具。

若要针对特定 platform 而非自动检测全部：

```bash
code-review-graph install --platform codex
code-review-graph install --platform claude-code
code-review-graph install --platform opencode
```

### 受支持的 Platforms

| Platform | Config file |
|----------|-------------|
| **Codex** | `~/.codex/config.toml` + `~/.codex/hooks.json` |
| **Claude Code** | `.mcp.json` + `.claude/settings.json` |
| **OpenCode** | `opencode.jsonc`（首选）或 `opencode.json` |

## 核心工作流

### 1. 构建 graph（仅首次）
```bash
code-review-graph build      # 完整构建
code-review-graph update     # 之后的增量更新
```
解析你的整个 codebase。500 个文件约需 10 秒。MCP client 中也可直接调用 `build_or_update_graph_tool`。

### 2. 审查变更（日常使用）
```
/code-review-graph:review_changes
```
仅审查自上次 commit 以来变更的文件，再加上 graph 衍生的 impact radius。相关的 review 和 impact 响应中包含紧凑的估算 `context_savings` 元数据。

### 3. 审查一个 PR
```
/code-review-graph:pre_merge_check
```
对 branch diff 进行全面的结构性 review，并带 blast-radius 分析。

### 4. Watch 模式（可选）
```bash
code-review-graph watch
```
每次保存文件时自动更新 graph。零手动操作。

### 5. 可视化 graph（可选）
```bash
code-review-graph visualize
open .code-review-graph/graph.html
```
交互式 D3.js force-directed graph。初始为折叠状态（仅 File nodes）——点击文件展开其 children。使用搜索栏过滤，点击图例中的 edge 类型可切换可见性。

### 6. 语义搜索（可选）
```bash
pip install "code-review-graph[embeddings]"
```
然后使用 `embed_graph_tool` 计算 vectors。`semantic_search_nodes_tool` 在存在匹配的 embeddings 时自动使用 vector 相似度，否则回退到 keyword/FTS 搜索。

Embedding providers 包括本地 sentence-transformers、OpenAI 兼容端点、Google Gemini、MiniMax 和 Voyage。本地 embeddings 使用 `CRG_EMBEDDING_MODEL`；OpenAI 兼容 providers 使用 `CRG_OPENAI_BASE_URL`、`CRG_OPENAI_API_KEY` 和 `CRG_OPENAI_MODEL`；Voyage 使用 `VOYAGE_API_KEY`，可选 `CRG_VOYAGE_MODEL`。Cloud providers 为 opt-in，除非设置 `CRG_ACCEPT_CLOUD_EMBEDDINGS=1`，否则会打印出 egress 警告。

Function/class 的文档摘要会包含在 embedding 文本中。对于由旧版本创建的 graph，在重新 embedding 前先运行一次完整 build，以便所有文件都获得该元数据。build/update/watch 之后的 embedding 刷新始终默认关闭；使用精确的 provider 和 model 选择启用，例如：

```bash
code-review-graph build \
  --embedding-provider local \
  --embedding-model all-MiniLM-L6-v2
```

同样的两个选项适用于 `update`、`postprocess` 和 `watch`。它们必须一起提供。刷新只会更新此前已 embedding 的 graph，拒绝将 vectors 迁移到不同的 provider/model/endpoint，清除已删除节点对应的 vectors，并将 provider 或传输失败降级为 graph-build 警告。

### 7. 用 risk scoring 检测变更（v2）
```
向你的 MCP client 提问："Review my recent changes with risk scoring"
```
使用 `detect_changes_tool` 将 diffs 映射到受影响的 functions、flows、communities 和测试缺口。

### 8. 探索 architecture（v2）
```
向你的 MCP client 提问："Show me the architecture of this project"
```
使用 `get_architecture_overview_tool` 生成基于 community 的 architecture 图，并带 coupling 警告。

### 9. 生成 wiki（v2）
```bash
code-review-graph wiki
```
在 `.code-review-graph/wiki/` 中为每个检测到的 community 创建 markdown wiki 页面。

### 10. Multi-repo 搜索（v2）
```bash
code-review-graph register /path/to/other/repo --alias mylib
```
然后使用 `cross_repo_search_tool` 在所有已注册的 repositories 中搜索。

## Context Savings（上下文节省）

CRG 通过发送 graph 衍生的结构性上下文而非大段的文件转储来减少 review context。具体减少量取决于 repository 和变更的形态。

自 v2.3.4 起，review 和 impact tools 包含紧凑的 `context_savings` 元数据。在 v2.3.5 中，CLI 在 `detect-changes --brief` 和 `update --brief` 上以带边框的 `Token Savings` 面板展示，含按类别细分（Functions / Tests / Risk / Other），其总和恰好等于 graph 响应大小。添加 `--verify` 可与 OpenAI 的 `cl100k_base` tokenizer 交叉核对显示的数字（需要 `pip install tiktoken`）。所有数字都标注为估算值，因为它们使用保守的近似而非针对具体模型的 tokenization；校准显示，该估算在整体上与实际 GPT-4 tokens 的误差保持在约 4% 以内。单文件的小变更偶尔会比原始文件消耗更多 context，因为 graph 元数据有开销。

## 受支持的语言

parser 当前覆盖 Python、JavaScript、TypeScript/TSX、Rust、C/C++、shell 脚本、Verilog/SystemVerilog、通过 TypeScript parser 解析的 Astro 文件，以及 Jupyter notebooks（`.ipynb`）。

无扩展名的脚本通过 shebang 检测常见的 bash/sh/dash/ash、Python、Node 解释器。

尚未覆盖的语言无需 fork 即可通过 `.code-review-graph/languages.toml` 配置添加——参见 [CUSTOM_LANGUAGES.md](CUSTOM_LANGUAGES.md)。

## 会被索引的内容

- **Nodes**：Files、Classes、Functions/Methods、Types、Tests
- **Edges**：CALLS、IMPORTS_FROM、INHERITS、IMPLEMENTS、CONTAINS、TESTED_BY、DEPENDS_ON

完整细节参见 [schema.md](schema.md)。

## Ignore 模式

默认情况下，以下路径会从索引中排除：

```
.code-review-graph/**    node_modules/**    .git/**
__pycache__/**           *.pyc              .venv/**
venv/**                  dist/**            build/**
.next/**                 target/**          *.min.js
*.min.css                *.map              *.lock
package-lock.json        yarn.lock          *.db
*.sqlite                 *.db-journal
```

要添加自定义模式，请在 repo 根目录创建 `.code-review-graphignore` 文件（语法与 `.gitignore` 相同）：

```
generated/**
vendor/**
*.generated.ts
```

在 git repos 中，索引基于已跟踪的文件（`git ls-files`），因此 gitignored 文件会被自动跳过。使用 `.code-review-graphignore` 来排除已跟踪的文件，或在 git 不可用时使用它。
