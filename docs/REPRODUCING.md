# 复现 Benchmarks

本文档给出精确的命令，用于复现 README 和 `diagrams/` 中显示的每个 benchmark 数字。两个人在不同日子的不同机器上运行下面的配方，应该产生完全相同的数字（在浮点舍入范围内）。

如果你得到不同的数字，那是个 bug——请提交一个 issue。

## 验证"saved tokens"数字

CLI 的 `Token Savings` 面板使用 `chars / 4` 近似值，标记为 `estimated: true`，而非针对具体模型的 tokenizer。该近似设计目标是既快（无模型加载、无推理）又保守。

### 如何对照真实 tokenizer 验证

```bash
pip install tiktoken
code-review-graph detect-changes --brief --verify
```

面板会新增一行 `Verified (tiktoken)`，显示用 OpenAI 的 `cl100k_base` tokenizer（GPT-4 家族）做的相同计算。如果估算偏差很大，你会立刻看到：

```text
┌───────────────────────── Token Savings ─────────────────────────┐
│ Full context would be:     12,921 tokens                        │
│ Graph context used:           762 tokens                        │
│ Saved:                     12,159 tokens (~94%)                 │
│ Verified (tiktoken):       10,835 tokens (~93%)  [11,611 → 776] │
│ Breakdown: Functions 244 · Tests 191 · Risk 244 · Other 83      │
└─────────────────────────────────────────────────────────────────┘
```

### 校准结果（已提交）

一次性的校准，跨 192 个文件 / 约 1.7 MB 的混合源码（Python、JS、TS、Rust、RST、MD），取自 5 个测试 repos：

| Repo | 样本文件 | bytes | chars/4 估算 | tiktoken 真实值 | 比率 est/real |
|---|---:|---:|---:|---:|---:|
| flask | 46 | 470,179 | 117,559 | 109,969 | 1.069 |
| fastapi | 38 | 156,224 | 39,072 | 34,897 | 1.120 |
| express | 23 | 296,805 | 74,207 | 83,575 | 0.888 |
| httpx | 38 | 254,184 | 63,556 | 62,909 | 1.010 |
| code-review-graph | 47 | 539,206 | 134,820 | 120,760 | 1.116 |
| **OVERALL** | **192** | **1,716,598** | **429,214** | **412,110** | **1.041** |

`chars / 4` 在整体上比真实 GPT-4 tokens 多约 **+4.1%**。按 repo 看，它在 **-11%**（express）到 **+12%**（fastapi：大量 docstrings 和类型注解）之间摆动，但**比率**趋于稳定，因为除法两边被同等地偏差影响。

用本 commit 中 `code_review_graph/context_savings.py:verify_with_tiktoken` 里的片段复现该校准，或在任意 commit 上直接运行 `--verify` flag。

## 什么是确定性的、什么不是

| 可复现 | 原因 |
|---|---|
| Tree-sitter 解析 | 输入字节的纯函数 |
| Node / edge 计数 | 以 `qualified_name` 为键的确定性 upsert |
| FTS5 BM25 分数 | 确定性 |
| CPU 上的 `all-MiniLM-L6-v2` embeddings | 模型权重在 HuggingFace 缓存中按 SHA 固定 |
| Leiden community IDs | 有种子——`communities.py` 中的 `_LEIDEN_SEED=42`，用 `CRG_LEIDEN_SEED` 环境变量覆盖 |
| `naive_corpus_tokens` | 对固定的 git checkout 是确定性的 |
| 在固定 SHA 上的 `git clone` | 决定源文本字节流 |

过去让它**不**可复现的东西（现已修复）：

- 每个 `code_review_graph/eval/configs/*.yaml` 中的 `commit: HEAD`——替换为每个 repo 固定的最新 test-commit SHA
- 当固定 SHAs 超出浅克隆窗口时，`git clone --depth 50` 会静默回退到错误的 commits——现在使用带显式 `returncode` 检查的完整克隆
- Leiden 使用未设种子的 RNG 运行——现在已设种子
- `nextjs.yaml` 是一个命名错误、在评估本 repo 的配置——重命名为 `code-review-graph.yaml`
- FTS5 被创建但从未被 eval 框架的 `full_build` 调用填充——`code_review_graph/eval/runner.py` 现在直接调用 `postprocessing.run_post_processing`

## 前置条件

- Python 3.10 或更高
- `git` 在 PATH 上
- 网络访问（克隆 5 个上游 repos 约需 600 MB）
- 约 3 GB 可用磁盘
- 对于 embedding 步骤：`torch` + `sentence-transformers` 另需约 700 MB

## 步骤 1——安装正确的 extras

```bash
git clone https://github.com/yanfeng98/nano-code-review-graph
cd code-review-graph

# eval extras：pyyaml + matplotlib（matplotlib 仅 `--report` 需要）
# embeddings extras：sentence-transformers + numpy
uv sync --extra eval --extra embeddings     # 或：pip install -e ".[eval,embeddings]"
```

## 步骤 2——运行正式 eval

这一步在固定 SHAs 上克隆 5 个上游 repositories，为每个构建完整 graph（parser + 跨文件 resolvers + signatures + FTS5 + flows + Leiden communities），然后运行 `token_efficiency`、`impact_accuracy`、`agent_baseline` 和 `multi_hop_retrieval` benchmarks。

```bash
uv run code-review-graph eval \
  --benchmark token_efficiency,impact_accuracy,agent_baseline,multi_hop_retrieval
```

失败语义（适用于每个 benchmark）：抛出的 tool 调用**不是**测量结果。该行保留在 CSV 中，带 `status=error` 用于取证，但从所有聚合中排除。（两个历史 bug 让失败看起来像胜利：抛出的 `get_review_context` 产生 `graph_tokens=0` 和 `naive/1` 的比率，抛出的 `analyze_changes` 静默设置 `predicted = changed`，保证了 recall 1.0。两者都已修复；回归测试位于 `tests/test_eval.py`。）

在 M1/M2 Mac 上的预期运行时间：build 阶段大约 8–15 分钟，加上每个 benchmark 数秒。

输出：

- `evaluate/test_repos/{express,fastapi,flask,httpx,code-review-graph}/`
- `evaluate/test_repos/<name>/.code-review-graph/graph.db`
- `evaluate/results/<name>_<benchmark>_<date>.csv`

## 步骤 3——生成 embeddings（独立 benchmark 需要）

独立的 token benchmark 内置 5 个硬编码的自然语言问题。没有 embeddings，hybrid search 无法匹配它们，benchmark 会静默返回 0× 削减比率（会打印响亮的警告）。

```bash
for repo in express fastapi flask httpx code-review-graph; do
  uv run code-review-graph embed --repo "evaluate/test_repos/$repo"
done
```

预期运行时间：总共 2–5 分钟。Vectors 位于同一个 `graph.db` 中。

## 步骤 4——运行独立 token benchmark

这个 benchmark 把 repo 中**所有源码文件的 tokens** 与每个样本问题的 **5 个搜索命中 + 一些邻居 edges** 对比。比率回答的是：*在一个典型问题上，graph 让我跳过多少 tokens？*

```bash
uv run python <<'PY'
import json
from pathlib import Path
from code_review_graph.graph import GraphStore
from code_review_graph.token_benchmark import run_token_benchmark

results = {}
for repo in sorted(Path("evaluate/test_repos").iterdir()):
    db = repo / ".code-review-graph" / "graph.db"
    if not db.exists():
        continue
    store = GraphStore(str(db))
    try:
        results[repo.name] = run_token_benchmark(store, repo)
    finally:
        store.close()

print(f"{'Repo':<22}{'naive_tokens':>16}{'avg_graph_tokens':>20}{'avg_ratio':>14}")
print("-" * 72)
for name, out in sorted(results.items(), key=lambda x: -x[1]["average_reduction_ratio"]):
    pq = out["per_question"]
    avg_graph = int(sum(r["graph_tokens"] for r in pq) / max(len(pq), 1))
    print(f"{name:<22}{out['naive_corpus_tokens']:>16,}"
          f"{avg_graph:>20,}{out['average_reduction_ratio']:>13.1f}×")

Path("evaluate/standalone_token_benchmark.json").write_text(json.dumps(results, indent=2))
PY
```

## Canonical 数字

<!-- BEGIN canonical-stats -->
捕获于 **2026-05-25**，macOS arm64、Python 3.11、sentence-transformers 5.5.1、`all-MiniLM-L6-v2`、`CRG_LEIDEN_SEED=42`。如果你的数字与舍入误差的差异更大，说明链路中有什么发生了漂移——提交一个 issue。

> 注：自捕获以来，fastapi 配置被重新固定到 `22381558`，gin 配置随 Go 支持一并移除。下表反映当前的 5-repo 配置；fastapi 行保留其 2026-05-25 的测量数值。

### 独立 token benchmark（`code_review_graph/token_benchmark.py`）

每行是 5 个样本问题的平均值（`how does authentication work`、`what is the main entry point`、`how are database connections managed`、`what error handling patterns are used`、`how do tests verify core functionality`）。

| Repo | snapshot SHA | naive_corpus_tokens | avg graph_tokens | avg ratio |
|---|---|---:|---:|---:|
| fastapi | `22381558` | 951,071 | 2,169 | **528.4×** |
| code-review-graph | `84bde354` | 208,821 | 2,495 | **93.0×** |
| flask | `a29f88ce` | 125,022 | 1,986 | **71.4×** |
| express | `b4ab7d65` | 135,955 | 3,465 | **40.6×** |
| httpx | `b55d4635` | 89,492 | 2,438 | **38.0×** |

跨 5 个 repos 的范围：**38× – 528×**。数字相比上次捕获有所下降，因为（a）测试 repos 现在被彻底清除/重新克隆——没有残留的构建产物或本地缓存虚增 naive baseline；以及（b）同一版本中每个 node 的 embedding 文本变得更丰富（参见 `embeddings._node_to_text`），因此 graph 响应本身稍大。两者都是对先前数字的正确性改进。

### 正式 `token_efficiency` benchmark（`code_review_graph/eval/benchmarks/token_efficiency.py`）

一个不同的分母：只是每个 commit 的**变更文件内容**，对比完整的 `get_review_context()` JSON。对于小提交，响应大于输入（它携带 impact-radius edges + 源码片段），所以这里的比率有意 < 1.0——那不是 bug，它测量的东西与独立 benchmark 不同。

原始 per-commit CSVs 位于 `evaluate/results/<repo>_token_efficiency_*.csv`。

### 影响准确性（`code_review_graph/eval/benchmarks/impact_accuracy.py`）

跨 5 个 repos 的 10 个 commits。Benchmark 并排放出两种 ground-truth 模式，由 `ground_truth_mode` CSV 列区分：

| 模式 | Ground truth | 它告诉你什么 |
|---|---|---|
| `graph-derived（circular——上限）` | 变更文件 + 有 CALLS/IMPORTS_FROM edges 指向它们的文件——**派生自预测器遍历的同一个 graph** | 一个上限。这里的 recall 1.0 部分是构造使然，不是独立证据。 |
| `co-change（同一 commit，排除种子）` | 给定一个种子文件，作者在同一 commit 中实际触碰的*其他*文件 | 来自 git 历史的近似独立证据。预期 recall 显著更低。 |

下面的 canonical 数字**仅以 graph-derived 模式捕获**（捕获时 co-change 模式还不存在）。把 recall 行视为循环上限，而非"100% recall"：

| 指标（graph-derived 模式——循环上限） | 值 |
|---|---|
| Recall（跨 10 个 commits 的均值） | **1.000**（每个 commit 的上限） |
| F1（均值） | **0.745** |
| F1（中位数） | 0.697 |
| F1（min / max） | 0.455 / 1.000 |

Canonical co-change 数字将在下一次完整捕获后加入——在测量之前我们不引用它们。单文件 commits 在 co-change 模式中以 `status=skipped` 记录（没有独立的东西可以评分）。

Blast-radius 分析在某些 commits 中过度预测（最坏情况下 precision ≈ 0.30，34 个文件被标记对应一次 10 文件变更）。这是有意的：漏掉一个依赖比多审查一个文件更糟。

### Multi-hop retrieval（`code_review_graph/eval/benchmarks/multi_hop_retrieval.py`）

跨 5 个 repos 的 9 个手工整理任务。每个任务是一个 2 步 tool 链：

1. `hybrid_search(nl_query, limit=10)` 寻找起始 anchor node。
2. `query_graph(<traversal_pattern>, target=<anchor>)` 沿 `callers_of` / `callees_of` / `tests_for` / `imports_of` 等走一跳。

任务**只有在** anchor 在 top-K 中被找到*并且* traversal 返回了预期的邻居名称时才**得 1.0**。否则**得 0.0**（这会把"搜索错过 anchor"和"traversal 返回了错误的集合"两种情况混为一谈——通过检查 per-task CSV 行中的 `anchor_found` 和 `neighbor_recall` 来拆分）。

| Repo | 任务 | Anchor 找到 | 排名 | 邻居召回 | 分数 |
|---|---|---|---:|---:|---:|
| code-review-graph | crg-parse-file-callers | yes | 0 | 1.00 | **1.00** |
| code-review-graph | crg-upsert-node-callers | yes | 4 | 1.00 | **1.00** |
| express | express-create-application-callees | yes | 1 | 1.00 | **1.00** |
| fastapi | fastapi-route-handler-callers | yes | 6 | 1.00 | **1.00** |
| fastapi | fastapi-get-dependant-callers | no | — | 0.00 | **0.00** |
| flask | flask-dispatch-callers | yes | 3 | 1.00 | **1.00** |
| flask | flask-exception-callers | yes | 5 | 1.00 | **1.00** |
| httpx | httpx-client-request-callers | yes | 0 | 1.00 | **1.00** |
| httpx | httpx-async-request-tests | yes | 7 | 1.00 | **1.00** |

**跨 9 个任务的平均分：0.889**。8/9 个任务通过；唯一失败的一个（`fastapi-get-dependant-callers`）针对一个拼写为 `get_dependant`（"dependant" 带 `a`）的函数，查询措辞为 "dependency declarations into a tree"——两者之间没有词法重叠，查询中也没有可提取的 identifier 供提升启发式锁定。保留为一次诚实的失败；修复方案要么是查询重写，要么是更丰富的 embedding 模型。

#### 分数如何从 0.545 提升到 0.909（当日修复）

v1 脚手架最初得分为 **0.545**（6/11）。两项改动把它带到 **0.909**（10/11），两项都是确定性的、都很小、都在同一次 session 中提交：

1. **`embeddings.py:_node_to_text`**——每个 node 的 embedding 文本过去只是 `"{name} {kind} in {parent}"`。现在它还包含点分形式（`APIRoute.get_route_handler`）、拆成单词的 identifier（`get route handler`）以及所在模块目录（`routing`、`fastapi`、`dependencies`）。所有 re-embedding 都是自动的——文本 hash 变化，`EmbeddingStore.embed_nodes` 会重新 embedding。大小写/分隔符规则参见 `_split_identifier`。

2. **`search.py:extract_query_identifiers`**——像 "Who advances the gin middleware chain via Context.Next" 这样的自然语言查询，现在会提取其中的 dotted / snake_case / CamelCase identifier tokens。`qualified_name` 包含任何提取出的 identifier 的搜索结果会获得 2.0× 提升。这把 `Context.Next` 从第 11 名推到了第 0 名。

剩下的 `fastapi-get-dependant-callers` 失败无法由这两项改动修复，因为查询与目标不共享任何 identifier 或子串——这正是启发式的边界。

移除 gin 配置后，当前 9 任务配置得分为 **0.889**（8/9）。分数从 0.909 降到 0.889 完全源于任务集缩小（删除了 gin 的两个总是通过的任务），而非对启发式的改动。

这个 benchmark 是一个 v1 脚手架（最初 11 个任务，当前配置 9 个）。意图是追踪**多跳 tool 链**作为 agent 的实际使用模式，而不只是单次检索。添加更多任务：按照下面的 schema 向 `code_review_graph/eval/configs/*.yaml` 下的任何配置追加 `multi_hop_tasks:` 条目：

```yaml
multi_hop_tasks:
  - id: my-task-id                # 必填，唯一
    nl_query: "natural language" # 必填，agent 会问什么
    anchor_qualified_suffix:     # 必填，预期 qualified_name 的小写后缀
      "rel/path.py::owner.symbol" #   （大小写不敏感的 endswith）
    traversal_pattern: callers_of # 可选 callers_of|callees_of|imports_of|
                                  # importers_of|tests_for|inheritors_of|children_of
    expected_neighbor_names:      # 必填，应出现在 traversal 结果中的裸名列表
      - "expected_one"
    k: 10                         # 可选，搜索步骤的 top-K 深度
```

### Build 统计

| Repo | Nodes | Edges | Flows | Communities | Embeddings | FTS idx rows |
|---|---:|---:|---:|---:|---:|---:|
| fastapi | 6,292 | 32,081 | 165 | 85 | 5,164 | 127 |
| express | 1,912 | 18,877 | 4 | 7 | 1,771 | 47 |
| code-review-graph | 1,418 | 8,877 | 104 | 11 | 1,326 | 38 |
| flask | 1,415 | 8,259 | 78 | 13 | 1,329 | 35 |
| httpx | 1,261 | 8,228 | 128 | 5 | 1,193 | 34 |

Embeddings 计数低于 node 计数，因为 File nodes 不做 embedding。FTS idx rows 远低于 node 计数，因为 FTS5 存储倒排索引段，而不是每个被索引文档一行。
<!-- END canonical-stats -->

## Agent baseline benchmark（`code_review_graph/eval/benchmarks/agent_baseline.py`）

独立 token benchmark 中的整语料库 baseline 是真实 agent 不会支付的上限。这个 benchmark 模拟没有 graph 时 agent 实际会做什么：

1. 从配置的 `agent_questions:` 列表中的每个问题推导搜索词（通过 `search.extract_query_identifiers` 得到 identifier 形状的 tokens，加上普通关键字；缺失时回退到 `search_queries` 的查询字符串）。
2. 对语料库做纯 Python grep（无外部 `rg`/`grep` 二进制），按总的大小写不敏感匹配次数对源文件排序（确定性；平局按路径打破）。
3. 读取前 3 个文件并做 token 计数（`chars/4`），作为 `baseline_tokens`。
4. 与同一问题的 graph-query 成本对比（5 个 hybrid search 命中 + 每个命中最多 5 条邻居 edges——与独立 benchmark 相同的核算方式）。

输出：`evaluate/results/<repo>_agent_baseline_<date>.csv`，每个问题带 `baseline_to_graph_ratio`。任一侧为零的行被标记为 `status=no_graph_results` / `status=no_baseline_match` 并从聚合中排除（`agent_baseline.aggregate`）。尚无 canonical 捕获；一旦捕获，数字会加入上面的 canonical 块——在测量完成前我们不引用它们。

## 每周 CI 运行（仅报告）

`.github/workflows/eval.yml` 每周一 06:23 UTC 运行（外加手动 `workflow_dispatch`），针对两个最小的固定配置（`httpx`、`flask`），使用 `token_efficiency`、`impact_accuracy` 和 `agent_baseline` benchmarks。它把 CSVs 作为 artifact 上传，并写一个 job-summary 表格。它刻意是**仅报告**：回归不会让默认分支失败。

## 哪个 benchmark 测量什么

repo 里有四个不同的"token" benchmarks。它们都有效，但测量不同的场景：

| Benchmark | Naive baseline | Graph 成本 | 回答的问题 |
|---|---|---|---|
| `code_review_graph/eval/benchmarks/token_efficiency.py` | 特定 commit 的**变更文件内容**之和 | 完整的 `get_review_context()` JSON | "graph 比只读 diffed 文件更便宜吗？" |
| `code_review_graph/eval/benchmarks/agent_baseline.py` | 该问题标识符的 **grep top-3 文件** | 每个问题 5 个搜索命中 + 5 条邻居 edges | "graph 比一个现实的 grep-and-read agent 更便宜吗？" |
| `code_review_graph/eval/token_benchmark.py` | 无——绝对 per-workflow 成本 | 5 个 MCP-tool 响应之和 | "一个完整的 agent workflow 要花多少 tokens？" |
| `code_review_graph/token_benchmark.py`（独立） | repo 中**所有源文件**之和 | 每个问题 5 个搜索命中 + 5 条邻居 edges | "graph 比读整个 repo 更便宜吗？" |

`code_review_graph/eval/benchmarks/token_efficiency.py` 的数字对小型 commits 可能**小于 1.0×**（`get_review_context` 携带 impact-radius 元数据和源码片段，会超过很小的变更文件集合）。独立 benchmark 的数字**总是很大**，因为 baseline 是整个 repo——这就是为什么 README 以中位数（~71×）打头并把 528× 当作最大值，以及为什么 `agent_baseline` 作为现实主义的中间地带存在。选择与你讨论的场景匹配的那个。

## 生成 diagrams

`diagrams/` 中的 9 个 diagrams 由 `diagrams/generate_diagrams.py` 生成。Excalidraw 源文件（`.excalidraw`）与渲染工具链（`export_pngs.mjs`、`render-entry.js`、`render-bundle.js`）都被 gitignored（`.gitignore` 中的 `*.excalidraw` 及 `diagrams/export_pngs.mjs` 等行）；只有渲染后的 PNGs 被跟踪。在 benchmark 刷新后重新生成：

```bash
# 1. 重新生成 .excalidraw 源（数字/语言/平台与 parser/README 对齐）
uv run python diagrams/generate_diagrams.py

# 2. 无头渲染 PNG（需要 Node ≥ 22 + Playwright Chromium，且已安装
#    @excalidraw/utils + esbuild；浏览器可复用 ~/.cache/ms-playwright 中的缓存）
cd diagrams
npm install @excalidraw/utils esbuild playwright   # 一次性
npx esbuild render-entry.js --bundle --format=iife \
  --platform=browser --define:process.env.NODE_ENV='"production"' \
  --outfile=render-bundle.js
node export_pngs.mjs                               # 渲染默认 3 张过期的（5/8/9）
# 或：node export_pngs.mjs all                     # 渲染全部 9 张
```

`export_pngs.mjs` 用 Playwright 打开内联了 `render-bundle.js` 的无头页面，通过 `@excalidraw/utils` 的 `exportToBlob` + `getDimensions` 回调做 uniform 4× 缩放（坐标与文字等比，等同 excalidraw.com 的导出倍率；Virgil 字体内嵌在 bundle 中，无需网络），产出的 PNG 与 excalidraw.com 同一渲染引擎保持一致。手动导出（在 excalidraw.com 打开每个 `.excalidraw`）仍可用作后备。

## 故障排查

**`git clone failed`**——网络或上游限流。修复方式是一次干净的 retry；eval 设计上不自动重试（响亮的失败 > 静默回退）。

**`git checkout <sha> failed`**——上游重写了历史或移除了该 SHA。带上失败配置提交一个 issue，这样我们可以重新固定。

**独立 benchmark 期间的 `No embeddings found in this graph` 警告**——你跳过了步骤 3。运行它。

**两次运行之间 community IDs 不同**——确保你在带种子的 `communities.py` 上。检查 `grep _LEIDEN_SEED code_review_graph/communities.py`。你可以用 `CRG_LEIDEN_SEED=<int>` 覆盖种子，但所有协作者必须同意相同的值。

**`naive_corpus_tokens` 与 canonical 表不同**——确保每个 `evaluate/test_repos/<name>` 内的 `git rev-parse HEAD` 与对应配置文件中的 `commit:` 字段匹配。如果不匹配，删除该克隆，让步骤 2 在固定 SHA 上重新克隆。
