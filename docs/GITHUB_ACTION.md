# GitHub Action：Risk-Scored PR Review

code-review-graph 附带一个复合 GitHub Action（repo 根目录的 `action.yml`），它会在每个 pull request 上发布一条 risk-scored、graph 感知的 review 评论——可以把它想象成一个托管式 AI review bot（Greptile 风格），但分析是**本地优先**的：知识图谱完全在你的 CI runner 上构建和查询，没有任何源码被发送到外部服务。

在每次 PR 运行时，action 会：

1. 从 PyPI 安装 `code-review-graph`。
2. 恢复缓存的 `.code-review-graph/` SQLite graph（或在 cache miss 时从头构建），并增量重新解析 PR 变更的文件。
3. 运行 `code-review-graph detect-changes --base origin/<base-branch>` 获取 risk-scored 的 functions、受影响的 execution flows 和测试缺口。
4. 渲染一份 markdown 报告（通过 `scripts/render_pr_comment.py`）并 upsert 一条置顶 PR 评论——每次 push 都更新同一条评论，因此 PR 线程永远不会被刷屏。
5. 可选地，在整体 risk score 越过阈值时让 job 失败（`fail-on-risk`）。

## 快速开始（外部 repositories）

```yaml
# .github/workflows/code-review-graph.yml
name: code-review-graph

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: tirth8205/code-review-graph@v2.3.7
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

这就完成了全部设置。Actions 提供的默认 `GITHUB_TOKEN` 就足够了——无需 PAT、无需 API key、无需第三方服务。

Self-hosted runners 必须是 2.327.1 或更新版本。该复合 action 使用基于 Node 24 的 GitHub actions，包括 `actions/setup-python@v7`、`actions/cache@v6` 以及推荐的 `actions/checkout@v7` 示例。

要把 review 变成 merge gate：

```yaml
      - uses: tirth8205/code-review-graph@v2.3.7
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          fail-on-risk: high
```

## 输入（Inputs）

| Input | 必填 | 默认值 | 描述 |
|-------|------|--------|------|
| `github-token` | 是 | — | 用于通过 GitHub API 发布置顶 PR 评论的 token。当 job 有 `pull-requests: write` 权限时，工作流的默认 `GITHUB_TOKEN` 即可。 |
| `comment` | 否 | `true` | 发布（并持续更新）置顶 PR 评论。设为 `false` 则只做分析/门禁而不评论。 |
| `fail-on-risk` | 否 | `none` | 当整体 risk score 达到某个级别时让 job 失败：`none`（从不失败）、`high`（risk ≥ 0.70）、`critical`（risk ≥ 0.85）。 |
| `python-version` | 否 | `3.12` | 用于运行 code-review-graph 的 Python 版本（支持 3.10+）。 |

## 输出（Outputs）

| Output | 描述 |
|--------|------|
| `comment-file` | 渲染好的 markdown 报告的 runner 本地路径。当由另一个受信任工作流发布时，与 `comment: false` 配合使用。 |

### 风险级别（Risk levels）

`detect-changes` 会产生一个 0.0–1.0 的整体 risk score（跨变更 functions 的最大值；评分因素见 `code_review_graph/changes.py:compute_risk_score`：flow 参与度、community 跨越、测试覆盖、安全敏感名称、caller 数量）。Action 把它映射为级别：

| Level | Score |
|-------|-------|
| low | < 0.40 |
| medium | 0.40 – 0.69 |
| high | 0.70 – 0.84 |
| critical | ≥ 0.85 |

## 评论包含的内容

- **整体风险** score 和 level，以及变更 functions、受影响 flows 和测试缺口的数量。
- **Risk-scored changes**——按 risk 排序的顶级变更 symbols 表格，带 file:line 位置和测试覆盖状态。
- **受影响的 execution flows**——变更触及哪些入口点 flows，按 criticality 排序。
- **测试缺口**——没有直接测试覆盖的变更 functions。
- **Token savings**——graph 支撑的报告相比完整读取每个变更文件省下了多少 tokens。这与 CLI 的 Token Savings 面板显示的 `context_savings` 估算相同（`chars / 4` 近似值，标记为 `estimated: true`——校准方法参见 [REPRODUCING.md](REPRODUCING.md)）。
- 一个 `Powered by code-review-graph` 页脚。

评论以一个隐藏的 HTML marker（`<!-- code-review-graph-report -->`）开头。Action 每次运行通过 `gh api` 查找该 marker，并 PATCH 现有评论而不是创建新评论（"置顶"评论）。

## 缓存行为

action 用 `actions/cache` 缓存 `.code-review-graph/` 目录（SQLite graph 数据库）：

- **Key**：`code-review-graph-schema9-<runner.os>-<hashFiles(lockfiles)>`，其中 lockfile hash 覆盖常见的 Python/JS/Rust lockfiles（`uv.lock`、`poetry.lock`、`requirements*.txt`、`package-lock.json`、`Cargo.lock`……）。
- **Schema 段**：`schema9` 追踪数据库 schema 版本（`code_review_graph/migrations.py` 中的 `LATEST_VERSION`）。schema 变化时它会递增，因此过期的缓存永远不会在不兼容的版本间被恢复。
- **恢复 keys**：回退到同一 OS 和 schema 的任何缓存，因此 lockfile 变化时仍能复用之前的 graph。
- **Cache hit 时**：action 运行 `code-review-graph update --base origin/<base-branch>`，它只重新解析与 PR base ref 不同的文件。如果恢复的数据库不可用，则回退到完整 `build`。
- **Cache miss 时**：运行完整 `code-review-graph build`（一次性成本；后续 PR 运行都是增量的）。

## 安全说明

- **Token 范围**：直接评论需要 `contents: read`（用于 checkout）和 `pull-requests: write`（用于发布评论）。在拆分式 fork 安全设置中，分析工作流只需要 `contents: read`；受信任的评论者只需要 `actions: read` 和 `pull-requests: write`。在每个工作流中只授予这些权限。
- **本地优先**：分析完全在 runner 上运行。没有代码、diff 或元数据离开 GitHub 的基础设施；没有外部 API、账号或 key。
- **不受信任的输入**：所有动态值（`github.base_ref`、PR 编号、action inputs）都通过环境变量传给脚本，绝不内插进 shell 命令。markdown 渲染器会转义表格/标记字符，并在 symbol 名称和文件路径进入评论正文之前剥离控制字符，此外还有服务端的 `_sanitize_name()` 净化。
- **固定版本**：从其他仓库消费该 action 时，把 `uses:` 固定到 release tag 或 commit SHA，而不是 `@main`。
- **Fork PRs**：来自 forks 的 `pull_request` 运行会收到只读的 `GITHUB_TOKEN`，因此它们无法直接发布评论。使用无特权的 `pull_request` 工作流配合 `comment: false`，把 `comment-file` 上传为 artifact，并从单独的受信任 `workflow_run` 工作流发布。参见 [`.github/workflows/pr-review.yml`](../.github/workflows/pr-review.yml) 和 [`.github/workflows/pr-review-comment.yml`](../.github/workflows/pr-review-comment.yml)。GitHub 从默认分支加载 `workflow_run` 工作流，因此受信任的评论半部分只有在那个工作流合并后才会激活。特权工作流必须验证源事件和分析的 commit，只在 `runner.temp` 下解压，限制并校验 artifact，并在发布前添加自己的置顶 marker。避免对 PR 代码做 checkout 的 `pull_request_target`，因为它可能用特权 token 执行不受信任的代码（[详情](https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/)）。

## Dogfooding

本仓库通过 [`.github/workflows/pr-review.yml`](../.github/workflows/pr-review.yml) 在自身 PR 上运行该 action，它以无写权限的方式运行本地 `action.yml` 并上传渲染好的报告。受信任的 [`pr-review-comment.yml`](../.github/workflows/pr-review-comment.yml) 工作流校验该 artifact 并发布置顶评论，而不 checkout 或执行 PR 控制的代码。

## 渲染脚本

markdown 渲染和 risk 门禁逻辑位于 [`scripts/render_pr_comment.py`](../scripts/render_pr_comment.py)（仅 stdlib，在 `tests/test_action_render.py` 中有单元测试），而非内联在 YAML 中，因此可以被测试和复用：

```bash
code-review-graph detect-changes --base origin/main | \
  python scripts/render_pr_comment.py            # markdown 输出到 stdout

python scripts/render_pr_comment.py --input report.json \
  --fail-on-risk high --quiet                    # 仅门禁：违规时以 exit 3 退出
```
