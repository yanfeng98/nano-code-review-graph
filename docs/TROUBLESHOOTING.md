# 故障排查

> **本 fork 不发布到 PyPI。** 下文出现的 `pip install code-review-graph` / `pipx`/`uvx` 安装命令都会解析到 **PyPI 上游原版**,而不是这份源码。本 fork 请用本地 editable:`git clone` 后 `uv sync --extra dev`,再以 `uv run code-review-graph …` 或 `.venv/bin/code-review-graph …` 调用;或构建本地 wheel 分发。

## 常见安装/设置问题的快速参考

四个问题涵盖了大多数支持咨询。先检查这些：

### 1. `.claude/settings.json` 中的 `Hooks use a matcher + hooks array` 错误

**你在一个 v2.2.3 之前的版本上。** v2.2.1 和 v2.2.2 发布了一个损坏的 hook schema——扁平的 `{matcher, command, timeout}` 条目缺少必需的嵌套 `hooks: []` 数组、以毫秒而非秒为单位的超时，以及一个并非真实 Claude Code 事件的 `PreCommit` event。PR #208（在 v2.2.3 中发布）重写了生成器，使其产出正确的 v1.x+ schema。

**修复：**

```bash
pip install --upgrade code-review-graph   # → v2.2.4 或更高
cd /path/to/your/project
code-review-graph install                 # 重写 .claude/settings.json
```

重新安装会把整个损坏的 `hooks` 块合并替换为新的嵌套格式，并往通过 `git rev-parse --git-path hooks` 解析出的 hooks 目录放入一个真实的 git pre-commit hook——通常是 `.git/hooks/pre-commit`，但链接的 worktrees 和 `core.hooksPath`（husky）环境也能处理。这就是"提交前检查"在 v2.2.3+ 中的位置，而不是在 Claude Code 设置里。

有效的 Claude Code hook events 是：`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、`SubagentStop`、`SessionStart`、`SessionEnd`、`PreCompact`、`Notification`。没有 `PreCommit`。

### 2. `pip install` 之后出现 `code-review-graph: command not found`

`pip install` 把 console script 放进了不在你 `$PATH` 上的 `bin/` 目录。四个修复方案，按推荐顺序：

**选项 1——本 fork 不发布到 PyPI（`pipx install code-review-graph` 会装上游）：**

```bash
# 用本仓库 editable：clone 后
uv sync --extra dev
uv run code-review-graph --help      # 或 .venv/bin/code-review-graph --help
```

`pipx` 在隔离的 venv 中安装 CLI 工具。如果之后仍然找不到命令，运行 `pipx ensurepath`，或把 `~/.local/bin` 加到你的 PATH。

**选项 2——本仓库不发布到 PyPI（不要用 `uvx`）：**

本 fork 无需也不应通过 `uvx code-review-graph` 获取工具——那会解析到 PyPI 上的上游包，而不是这份源码。请在本仓库内 `uv sync --extra dev`，再用 `uv run code-review-graph …` 或 `python -m code_review_graph …` 调用（见选项 3）。

**选项 3——作为 Python 模块运行（始终有效）：**

```bash
python -m code_review_graph install
python -m code_review_graph build
```

**选项 4——手动修复 PATH：**

```bash
pip show code-review-graph | grep Location
# 找到同级的 `bin/` 目录；在 macOS 用户安装中通常是
# ~/Library/Python/3.X/bin。把它加到你的 shell rc：
echo 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 3. code-review-graph 是项目级还是用户级？

**两者都是**——四个不同的部分，各自的 scope 不同：

| 部分 | Scope | 位置 |
|------|-------|------|
| Python 包 | 用户级 | 通过本仓库 `uv sync --extra dev`（editable）或本地 wheel 安装一次 |
| Graph 数据库 | 项目级 | 每个项目内的 `.code-review-graph/graph.db` |
| MCP server 配置（`.mcp.json`） | 项目级 | Claude Code 为每个项目启动一个 MCP server，`cwd=<project>` |
| Multi-repo registry | 用户级 | `~/.code-review-graph/registry.json`（仅用于 `cross_repo_search`） |

**简而言之**：安装工具**一次**，然后在每个你想要 graph 感知 review 的项目内运行 `code-review-graph install && code-review-graph build`。

### 4. 使用 venv？你必须手动更新 `settings.json`

`.claude/settings.json` 中的 Claude Code hooks 和 MCP tool 路径在**安装时被硬编码**。如果你在运行 `code-review-graph install` 之后切换（或创建）了一个虚拟环境，这些路径仍会指向旧解释器，server 会静默失败或使用错误的 Python。

**修复——把 `.mcp.json` 中的 `command`/`args` 以及 `.claude/settings.json` 中的任何 hook 命令更新为匹配你的 venv：**

```json
// .mcp.json —— 指向本仓库可导入的包（本 fork 不发布到 PyPI，请勿用 uvx）
{
  "mcpServers": {
    "code-review-graph": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "code_review_graph", "serve", "--auto-watch"]
    }
  }
}
```

或者简单地在**已激活的 venv 内部**重新运行 `code-review-graph install`，让路径被正确重新生成：

```bash
source .venv/bin/activate          # 先激活你的 venv
code-review-graph install          # 重写 .mcp.json 和 hook 路径
```

然后完全退出并重新打开 Claude Code，让它读取新配置。

### 5. "我构建了 graph，但 Claude Code 在新 session 里看不到它"

最可能的原因，按可能性排序：

1. **你在 `install` 之后没有重启 Claude Code。** Claude Code 在启动时读取 `.mcp.json`——如果你在某个 session 里运行了 `install`，请完全退出并重新打开 Claude Code，让 MCP server 注册。
2. **新 session 的 `cwd` 是另一个目录。** MCP server 以 `cwd=<project>` 启动，并从那里读取 `.code-review-graph/graph.db`。如果你的新 session 是在父文件夹或其他项目打开的，它找不到你构建的 graph。
3. **你运行了 `build` 但没有运行 `install`。** `build` 创建 `graph.db`；`install` 才是通过 `.mcp.json` 把 MCP server 注册到 Claude Code 的命令。两者都需要。
4. **MCP server 在启动时崩溃。** 在 Claude Code 内运行 `/mcp` 查看 server 状态，或在 macOS 上检查 `~/Library/Logs/Claude/mcp*.log`。

**快速检查清单：**

```bash
cd /path/to/your/project
code-review-graph status    # 应从构建的 graph 打印 Files/Nodes/Edges
ls .mcp.json                # 应该存在
cat .mcp.json               # 应该引用 `code-review-graph serve`
# 然后：完全退出 Claude Code，并在此项目内重新打开
```

如果 `status` 显示 graph，但新 session 中的 `/mcp` 没有列出 `code-review-graph`，说明 `.mcp.json` 不在该 session 的 `cwd` 中——从正确的项目根目录重新运行 `code-review-graph install`。

---

## 数据库锁错误
Graph 使用带 WAL 模式的 SQLite。如果看到锁错误：
- 确保同一时间只运行一个 build 进程
- 数据库会自动恢复；直接重试即可
- 如果损坏，删除 `.code-review-graph/graph.db-wal` 和 `.code-review-graph/graph.db-shm`

## 大型 repositories（>10k 文件）
- 首次 build 可能需要 30-60 秒
- 后续增量更新很快（<2s）
- 向 `.code-review-graphignore` 添加更多 ignore 模式：
  ```
  generated/**
  vendor/**
  *.min.js
  ```

## build 后缺失 nodes
- 检查文件的语言是否受支持（参见 [FEATURES.md](FEATURES.md)）
- 检查文件是否被某个 ignore 模式匹配
- 使用 `full_rebuild=True` 运行，强制完整重新解析

## Graph 似乎过期
- Hooks 会在编辑/提交时自动更新
- 如果过期，手动运行 `code-review-graph update`（或让 MCP client 调用 `build_or_update_graph_tool`）
- 检查 hooks 是否在 `.claude/settings.json` 中配置（重新运行 `code-review-graph install` 以重新生成）

## Embeddings 不工作
- 用 `pip install "code-review-graph[embeddings]"` 安装
- 运行 `embed_graph_tool` 计算 vectors
- 首次 embedding 运行会下载模型（约 90MB，一次性）

## MCP server 无法启动
- 验证 `uv` 已安装（`uv --version`；用 `pip install uv` 或 `brew install uv` 安装）
- 检查 `python -m code_review_graph serve` 能否无错误运行（本 fork 不发布到 PyPI，请勿用 `uvx code-review-graph`）
- 如果使用自定义 `.mcp.json`，确保 `command`/`args` 指向本仓库可导入的包（`python -m code_review_graph serve`，绝对解释器路径最稳）
- 重新运行 `code-review-graph install` 以重新生成配置

## Windows / WSL

- 如果 `daemon status` 以 WinError 87 崩溃（#511），或 CLI `detect-changes` 在 Windows 上映射出 0 个 functions（#528），升级到 v2.3.6+——两者都在那里修复
- 向 MCP tools 传 `repo_root` 时，路径中使用正斜杠
- 在 WSL 中，确保 `uv` 安装在 WSL 内部（而非 Windows 版本）：`curl -LsSf https://astral.sh/uv/install.sh | sh`
- 如果安装后找不到 `uv`，把 `~/.cargo/bin` 加到你的 PATH
- 由于文件系统事件限制，WSL1 上的文件监听（`code-review-graph watch`）可能有延迟；推荐使用 WSL2
- 在原生 Windows（非 WSL）上，可能需要启用长路径支持：`git config --system core.longpaths true`

## Community detection 需要 igraph

- 用 `pip install "code-review-graph[communities]"` 安装
- 没有 igraph 时，community detection 回退到基于文件的 grouping（精确度较低但仍可用）

## 带 LLM 摘要的 Wiki 生成

- 用 `pip install "code-review-graph[wiki]"` 安装
- 需要运行中的 Ollama 实例来生成 LLM 摘要
- 没有 Ollama 时，wiki 页面仅以结构信息生成（无文字摘要）

## 可选依赖组

如果某个 tool 返回 ImportError，安装相应的可选组：
- `pip install "code-review-graph[embeddings]"` 用于语义搜索
- OpenAI 兼容 embeddings 使用 stdlib HTTP clients，只需要各自的环境变量
- `pip install "code-review-graph[communities]"` 用于基于 igraph 的 community detection
- `pip install "code-review-graph[enrichment]"` 用于通过 Jedi 的 Python call-resolution enrichment
- `pip install "code-review-graph[wiki]"` 用于 wiki LLM 摘要（ollama）
- `pip install "code-review-graph[all]"` 用于全部功能
