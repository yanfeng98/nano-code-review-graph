# 维护者对账——2026-07-17

状态：本地与远程 CI 验证完成；等待维护者审查。

Base：`main` 位于 `b72413c`  
集成分支：`codex/reconcile-open-contributions-2026-07-17`  
跟踪 issue：`crg-nqi`

## 成果

该分支是一次刻意窄范围的、对独立有用且有证据支撑的修复的对账。它不是 release 分支，也不会整体合并任何大型贡献。在补丁已经是最强实现的地方保留了贡献者的 commits；冲突解决保留当前 `main` 的行为，并在下方注明。

审计快照覆盖：

- 每个本地分支、worktree、stash、已跟踪变更和未跟踪路径；
- 全部 104 个开放的 pull requests，使用分页的实时数据而非单页搜索结果；
- 全部 84 个开放的 issues（排除 pull requests）；
- 全部 29 个仓库讨论；以及
- 仓库知识图谱、受影响的 flows、tests、release notes 和当前的 CI/review 证据。

该分支不关闭任何远程 issue 或源 pull request。这些操作只应在本集成通过审查并合并之后进行。

## 保留与安全记录

主 checkout 保持在 `main` 的 `b72413c`，与 `origin/main` 相等。它的 31 个未跟踪路径未被移动、清理、暂存或重写：

- 26 个 iCloud 后缀的 `* 2.*` 副本与已跟踪文件逐字节一致；以及
- 五个唯一的本地产物仍为 checkout 私有：`.codex/`、一份本地转录稿、`OC3_TECHNICAL_CONTRIBUTION.md`、其 PDF 和 `PRESENTATION_BRIEF.md`。

三个 stashes 全部保留：

- `stash@{0}`——来自已合并 PRs 的 CI lint/test 修复；
- `stash@{1}`——本地 `uv.lock` 升级；以及
- `stash@{2}`——scaling/token-efficiency 的 mypy 修复。

所有预先存在的 worktrees 和 branches 都被保留，包括 `claude/hungry-morse`、`fix/incremental-flow-path-mismatch`、`release/v2.3.7`、`release/v2.4.0`、`review/local-fixes`、旧的 workflow 分支，以及它们的未跟踪 worktree 文件。对账只在 `.claude/worktrees/codex-reconciliation` 中执行。

重要的本地分支结论：

- `review/local-fixes` 是保留来源，而非合并候选。它有用的 TESTED_BY 工作已被提取。它的增量路径工作已在真实 node 替换生命周期下被证伪；不安全的 PID 清理、过宽的 ignore 规则、裸 C++ header 嗅探和 scoped-call 误报也仍被排除。
- `release/v2.4.0` 是 PR #559 的 head。它的 token-budget、doctor、eval 和 installer 表面仍然耦合，并存在正确性/供应链阻塞。选取了四个 patch 等价的 commits：三段式 TESTED_BY 系列和独立的 Action 路径渲染修复。
- `release/v2.3.7` 是 PR #559 加一次版本降级，绝不能作为 release candidate 合并或推送。
- `issue-194-specific-exception-logging` 与 `main` 上已有的工作在 patch 级别等价；多词搜索分支已被取代或需要拆分。

## 已选取的集成

| 分支 commit(s) | 来源 | 决定与证据 |
| --- | --- | --- |
| `34c5d00` | PR #564 | 在两个模板中使用 `#graph-svg` 而非页面级 `svg` 选择器；携带聚焦的回归测试。 |
| `d8e5453` | PR #565 | 移除机器专属 hook 路径，添加 PATH guard，并避免把 Bash hooks 应用到无关 tools。 |
| `cbf9355` | PR #573 | 把 PHP `use`、分组 imports、aliases、functions 和 constants 解析到本地文件；保留贡献者署名。 |
| `ddc8544`、`918ef13`、`580205d` | PR #559 commits `278e400`、`03e319e`、`a11dc04` 的精确 patch 等价物 | 在每个选中的消费点修正 TESTED_BY 方向、更新 dead-code 分析，并添加从 parser 到 store 到 query 的回归。这吸收了 #527 的工作并取代重叠的 PR #598。 |
| `6ece151` | PR #559 commit | 在 Action 评论中渲染仓库相对路径，而不带 release 分支的其余部分。 |
| `771307e` | issue #612 | 捕获裸、成员、链式和 null-conditional 的 C# 接收者调用并给出正确的 caller 归属；以 red/green 方式实现并带聚焦测试。 |
| `eeef686` | issue #613 | 通过真实的 MCP wrapper 保持打包文档回退可用；以 red/green 方式实现并带 installed-layout 回归。 |
| `571f665` | PR #578 的内容等价/rebased 移植 | 用字符串感知扫描器替换 regex JSONC 剥离，使 URLs 和类似注释的字符串内容得以保留；import 邻域上下文与源补丁不同。 |
| `df87b60`、`e5f563b` | PR #563 | 生成 [Claude Code skills 文档](https://code.claude.com/docs/en/skills)所要求的大写 `SKILL.md` 文件名并更新回归。这不采纳 PR #562 对显示名称做不必要小写化的做法。 |
| `90408c9` | PR #354 | 拒绝并保留有效的顶层数组/标量，同时把空/仅注释配置视为全新对象。冲突解决保留了 PR #578 更强的字符串感知 JSONC parser。#312/#350 的生产修复被有意省略，因为它们已在 `main` 上；它们的回归测试保留。 |
| `0abd789` | PR #353 | 使用既有的 metadata 形状持久化 Kotlin/C# 注解，并解析 C# namespace importers。这不声称解决 #310 中剩余的 impact-radius 设计。 |
| `b9ec19d` | PR #393 | 修复宣传中的 Zig 解析，并添加 structure/call/import/test fixtures。冲突解决保留了 `main` 上较新的 Nix 实现。 |
| `fc549ae` | 对账审查修复 | 当其嵌套 server 集合类型错误（array/object）时，逐字节保留现有 platform 配置；red/green 覆盖同时演练两种 schemas。 |
| `d611a2d` | 对账审查修复 | 为源内 Zig tests 生成 TESTED_BY（与文件名无关），并在嵌套 C# namespaces 中携带有效的 parent names；两个缺口都在实现前复现。 |
| `c7d7211` | 对账审查修复 | 用显式 stack 替换递归 C# namespace 发现；一个 1,200 层的 AST 回归在改动前失败，改动后通过且不截断 namespace 元数据。 |

最终 diff 大小和仓库级验证结果记录在下方。

## Pull-request 清单与处置

实时分页返回 104 个开放 PRs：第 1 页 100 个，第 2 页 4 个。它们都针对 `main`；102 个非 draft，而 #582 和 #618 是 drafts。每个开放 PR 在下方的路由清单中恰好出现一次。

- 已选区或直接重叠的工作（24）：#621、#618、#611、#601、#598、#586、#583、#582、#578、#573、#572、#568、#566、#565、#564、#562、#559、#538、#530、#527、#477、#354、#353、#92。
- Parser/语言工作（29）：#614、#602、#591、#590、#589、#580、#577、#560、#539、#526、#522、#517、#516、#514、#462、#459、#393、#415、#339、#338、#337、#333、#332、#331、#330、#329、#328、#252、#95。
- Graph/搜索/性能/产品工作（25）：#615、#606、#605、#604、#603、#600、#599、#581、#555、#552、#536、#509、#468、#460、#458、#457、#452、#394、#341、#340、#336、#335、#334、#327、#326。
- Platform/安装/CI/依赖/文档工作（26）：#617、#597、#596、#595、#584、#563、#557、#556、#554、#548、#547、#546、#545、#544、#543、#542、#540、#531、#505、#495、#491、#453、#449、#373、#347、#129。

路由分组不是笼统批准。重要的未选取决定：

- PR #559 整体合并不安全。它宣传的硬 token 上限只约束 snippets：一次禁用源、名义 6,000 token 上限的 44 文件运行仍返回了大约 167 万个字符。精简默认会隐藏它自己的 prompts 和恢复文本所要求的 tools。Eval 在忽略失败后可能复用过期结果；doctor 可能报告虚假健康并变更数据库；installers 会执行浮动的网络内容。独立的 Beads issues `crg-1nx` 和 `crg-4ys` 跟踪重新设计。
- PR #601 的裸端点 resolver 与 TESTED_BY 方向修复互补，但它在没有 import 证据的情况下激活全局唯一名称解析，并实质性改变 graph communities。采用前需要做精度和性能评估。
- PR #568 及相关的本地 scoped resolver 可以仅凭唯一性制造全局 `Class.method` edges，并增加全表扫描工作。它们仍被排除，等待 scoped 身份语义。
- PR #586 防止行丢失，但仍把歧义的重载调用绑定到第一个定义。稳定 symbol 身份在 `crg-lw5` 中跟踪。
- PR #611 看似避免了 embedding import 竞争，但增加了约七秒的急切启动延迟。它需要并发覆盖和明确的延迟决定。
- Draft PR #618 在 Git 路径上比 #566 更强，因为它使用 NUL 分隔的 bytes 和 `os.fsdecode`；在它的 draft/CI 状态及与分支/已跟踪输出行为重叠解决之前，它保持独立。
- PR #621 是聚焦的 Windows Codex-hook 候选，但 target-native 命令执行未被该分支的 Linux CI 覆盖。它的贡献者补丁已从本集成移除，移到专门的 [draft PR #626](https://github.com/tirth8205/code-review-graph/pull/626) 做 Windows 测试。
- PRs #595、#597 和 #596 构成一个前景看好的 Windows daemon 序列，但它们需要真正的 Windows 执行，不应藏在这个跨平台对账内部。
- PR #615 包含一个可信的小型继承文件描述符修复，但没有回归。先复现僵尸进程失败并添加一个。
- PR #477 包含有用的第二模板可视化工作，但在生成的 JavaScript 中输出一个字面转义引号。PR #564 是安全子集；剩余行为需要浏览器/`node --check` 覆盖。
- PRs #457 和 #552 有相同的 head 和一个说明不充分的三秒缓存 key。PRs #458 和 #460 是过期/无法合并的 token 替代方案；#604 增加了一个宽泛的 provenance 表面；#536 增加了一个大型可选 DSL。这些需要隔离的产品/API 审查。
- PRs #326–#341 是一个累积的过期堆栈，其尖端包含大量过时的删除。宽泛的 parser/framework PRs、platform 集成、依赖、翻译和产品功能仍是独立的审查单元，而不是打包在这里。
- PRs #556/#557 解决 fork-PR 评论，但需要干净的移植、显式的 `actions: read` 和 `issues: write` 权限、actionlint 和 fork 安全验证；#557 的原始 head 还包含无关的 parser/package-lock 变更。
- PR #491 的 uninstall 设计可以删除用户拥有的 Cursor 脚本、遗漏 Gemini MCP 状态、不安全地解析 JSONC，并重复 platform 清单。
- PR #459 可能为每个文件生成一个 parser-probe 子进程。PR #394 是可选的纵深防御，因为受支持的 FastMCP 版本已经对同步 handlers 做了 threadpool。

CI 证据稀疏：在审计快照时只有 PR #559 同时有成功的 CI 和 PR Review 运行。许多 fork workflows 显示 `action_required`，这既不是通过也不是失败。贡献者报告的结果被视为支持性证据，绝不替代对该合并分支的验证。

## 开放 issue 清单

全部 84 个开放 issues 都被读取并恰好分类一次：

- 已确认/可行动（21）：#623、#622、#620、#619、#616、#613、#612、#610、#609、#585、#579、#576、#500、#475、#473、#461、#343、#310、#291、#173、#63。
- 本地/release 部分或已修复（18）：#574、#569、#567、#561、#558、#553、#551、#550、#549、#537、#534、#523、#515、#497、#463、#450、#419、#295。
- 已在 `main` 上解决或待 release（10）：#524、#471、#243、#218、#212、#190、#132、#91、#87、#83。
- 支持/重测（5）：#474、#314、#262、#209、#189。
- 功能积压（25）：#607、#593、#592、#588、#587、#521、#518、#504、#482、#478、#436、#434、#430、#429、#369、#348、#346、#320、#311、#305、#269、#265、#232、#210、#199。
- 证据/讨论不足（5）：#535、#532、#506、#492、#426。

选中的补丁解决或实质性推进了 #523（可视化）、#549 和 #558（可移植 hooks）、#574（PHP imports）、#515（通过 #559 子集的 TESTED_BY）、#553（JSONC）、#612、#613 和 #295。PR #353 只推进 #310 的 namespace importer 部分；它的 impact-radius/detect-changes BFS 仍然开放。Issues #561 和 #567 因 PRs #562 和 #568 缺席而未处理。Issue #622 的冲突/重载问题被有意推迟，因为开放补丁不是完整的身份模型。Issues #619、#616 和 #610 分别需要独立的 API、platform-discovery 和启动延迟决定。

Issue #569 仍然开放。被审计的本地/PR #572 变体在增量重新解析已经替换 node IDs 之后才规范化路径；因此现有的 flow 和 community memberships 引用已删除的 nodes，且修改过的文件仍可能被跳过。生命周期感知的修复需要一个改变 graph 拓扑的回归，而不只是一个路径格式 fixture。

## 讨论清单

全部 29 个讨论都被枚举并阅读。具有直接工程含义的线程是 #501、#464、#137、#376、#355、#414、#410、#318、#467、#479 和 #405：

- #467 是精简 tool 表面的真实证据，但不验证 PR #559 当前的 cap 实现。
- #318 和 #410 支持可信的 status/doctor UX，同时强化了诊断必须非变更且诚实地失败的要求。
- #501 支持可移植的 PowerShell/Codex hooks，并为 PR #621 的专门验证路径提供了信息；#405 显示 hook 契约仍需要更清晰的文档。
- #464 和 #137 强化了 worktree/monorepo 安全的路径和 registry 行为。
- #376 和 #355 强化了显式的包含/排除语义；它们不证明用宽泛 ignore 模式隐藏源码路径是正当的。
- #414 为扩展性主张提供信息，#479 支持修复两个可视化模板而不仅是第一个页面形状。

其余的支持、设置、产品或公告讨论是 #525、#411、#105、#375、#109、#254、#206、#111、#131、#89、#186、#178、#134、#113、#101、#96、#85 和 #84。它们提供文档/积压上下文，但没有额外变更可安全地耦合进该分支。

## 后续跟踪与合并顺序

审计创建了聚焦的 Beads issues，而不是把未解决的工作藏在一个大分支里：

- `crg-1nx`——重新设计 v2.4 token 预算和精简 tool 表面；
- `crg-4ys`——拆分/加固 doctor、eval 和 installers；
- `crg-ys0`——从 `review/local-fixes` 移除不安全的阻塞项；
- `crg-lw5`——为冲突/重载设计稳定 symbol 身份；
- `crg-o1d`——修复跨增量 node-ID 替换的 #569；
- `crg-dtv`——关闭覆盖警告暴露的 SQLite 连接；
- `crg-8u4`——从 sdist 排除仅维护者使用的 `.beads` hooks；以及
- 现有的 platform/performance issues 仍是 Windows daemon、HOME 隔离和 daemon-stop 行为的负责人。

推荐的审查顺序：

1. path/edge 语义及其端到端测试；
2. 按语言的 parser 变更（PHP、C#、Kotlin、Zig）；
3. skills/config/hook 兼容性和 Windows CI；
4. 可视化、Action 渲染和打包文档；
5. 仅在合并后核对 release-note 准确性及潜在的源 PR/issue 关闭。

## 验证记录

在组装后的分支上完成：

- 最终 Python 3.13 套件（排除已知的原生 WatchDaemon 失败）：`1,447 passed`、`13 deselected`、`2 xpassed`；
- 隔离的 CI 等价覆盖运行：`1,446 passed`、`1 skipped`、`13 deselected`、`2 xpassed`；覆盖率 `72.95%`，阈值为 `65%`；
- 合并的 skills/多语言回归运行：`501 passed`，外加最终的 C# namespace 回归类：`6 passed`；
- ruff：干净；mypy：62 个源文件无问题；Bandit：无问题；
- Python 和 VS Code schema 版本均为 `9`；
- wheel 和 sdist 构建成功，且两者都包含 docs 回退所需的打包 `LLM-OPTIMIZED-REFERENCE.md`；
- 完整知识图谱重建：181 个解析文件、3,415 个 nodes、24,940 条 edges、200 个 flows、16 个 communities，无构建错误；
- graph review：25 个变更文件，risk score `0.65`，26 个受影响的 flows；parser 广度是主要的 blast radius，并收到两次独立审查外加聚焦的语言回归；以及
- draft PR #624：lint、mypy、Bandit、schema sync、PR Review、GitGuardian 以及 Python 3.10、3.11、3.12 和 3.13 测试 jobs 全部通过；以及
- `git diff --check`：干净。

独立审查首先发现五个 P1/P2 缺口：两个 #569 生命周期缺陷被移除，而 nested-config、Zig TESTED_BY 和嵌套 C# 用例以 red/green 方式修复。第二遍发现深层 C# 递归失败；那个也以 red/green 修复。没有其他 P1/P2 发现残留。

macOS Python 3.13 baseline 在 `TestWatchDaemon` 中存在原生的 watchdog/FSEvents `SIGBUS`，在 `main` 和集成分支上都存在。它在 `crg-229` 中跟踪，并从宽泛对比运行中排除；绝不能把它表述为这里引入的回归。

隔离覆盖运行发出 29 个针对未关闭 SQLite 连接的 `ResourceWarning`s；`crg-dtv` 跟踪把这些警告变成确定性的关闭。包检查还发现 sdist 中预先存在的仅维护者使用的 `.beads` hooks；`crg-8u4` 跟踪 manifest 策略修复。两者都没有被隐藏为通过的声明。

PR #621 的 Windows hook 补丁有意不包含在本集成中。它保留在 [draft PR #626](https://github.com/tirth8205/code-review-graph/pull/626)，直到 target-native CI 和维护者审查验证命令执行、stdin 排空、失败行为以及从现有仅 Unix hook 条目的升级。
