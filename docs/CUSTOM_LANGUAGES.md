# 自定义语言（Bring Your Own Language）

code-review-graph 内置了约 13 种语言的 parsers，但它所依赖的 [tree-sitter-language-pack](https://github.com/Goldziher/tree-sitter-language-pack) 捆绑的 grammars 远多于内置列表。如果你的 repo 使用了 graph 尚未覆盖的语言——Erlang、Haskell、OCaml、Fortran、Ada、Clojure……——你可以用一个小配置文件教会 parser 处理它。无需 fork、无需改代码。

## 快速开始

创建 `<repo_root>/.code-review-graph/languages.toml`：

```toml
[languages.erlang]
extensions = [".erl"]
grammar = "erlang"
function_node_types = ["function_clause"]
class_node_types = ["record_decl"]
import_node_types = ["import_attribute"]
call_node_types = ["call"]
comment = "Erlang via the bundled tree-sitter-erlang grammar"
```

然后重建：

```bash
uv run code-review-graph build
```

匹配所配置扩展名的文件现在会使用命名的 grammar 解析，产生的 Function/Class nodes 和 CALLS/IMPORTS_FROM edges 会像内置语言一样流入每个下游功能（impact radius、搜索、communities、wiki、MCP tools）。Nodes 的 `language` 字段会带上自定义语言名称（这里是 `erlang`）。

## Schema 参考

每个自定义语言是一个 `[languages.<name>]` 表。

| Key | 类型 | 必填 | 含义 |
|-----|------|------|------|
| `<name>` | table key | 是 | 存储在解析出的每个 node 上的语言标识符。小写字母、数字、`_`、`-`；最长 32 字符；必须以字母开头。 |
| `extensions` | string 列表 | 是 | 要认领的文件扩展名，每个都以点开头（例如 `".erl"`）。大小写不敏感匹配。 |
| `grammar` | string | 是 | 由 `tree_sitter_language_pack` 提供的 grammar 名称（探测可用性——见下文）。 |
| `function_node_types` | string 列表 | 否* | 定义 functions/methods 的 Tree-sitter node types。匹配的 nodes 变成 `Function` nodes（当名称/文件看起来像 test 时变成 `Test` nodes）。 |
| `class_node_types` | string 列表 | 否* | 定义 classes/records/types 的 node types。匹配的 nodes 变成 `Class` nodes。 |
| `import_node_types` | string 列表 | 否* | 用于 import/include 语句的 node types。每个产生一条 `IMPORTS_FROM` edge。 |
| `call_node_types` | string 列表 | 否* | 用于 call 表达式的 node types。每个从包围它的 function 产生一条 `CALLS` edge。 |
| `name_field` | string 或 string 列表 | 否 | 当定义的名称不在 `name` field 或普通的 `identifier` child 中时，用于定位定义名称的有序候选（见下文）。 |
| `comment` | string | 否 | 供人阅读的自由格式说明；parser 忽略。 |

\* 四个 node-type 列表中至少有一个必须非空，否则该条目会被跳过（没有可提取的内容）。

### 校验规则（安全第一）

loader 绝不会让一次 build 崩溃。任何无效项都会被跳过，并打印一条 `WARNING` 日志：

- **内置语言始终优先。** 自定义语言不能认领内置扩展名（`.py`、`.ts`、`.rs`……），也不能复用内置语言名称（`python`、`typescript`……）。
- `grammar` 必须能从 `tree_sitter_language_pack` 加载；未知 grammars 会被跳过。
- 每个扩展名必须以点开头。
- 两个自定义语言不能认领同一个扩展名（先到先得）。
- 每个 repo 最多加载 **20** 个自定义语言。
- 格式错误的 TOML 会为那次 build 禁用自定义语言（并给出警告）。
- `name_field` 必须是 string 或非空 strings 列表（最多 8 个候选）；其他任何形式都会跳过该条目并给出警告。

### 用 `name_field` 命名定义

默认情况下，parser 从 `identifier` 之类的 child 或字面上叫 `name` 的 field 中找到定义的名称。许多 grammars 把名称放在别处——一个命名不同的 field，或嵌套在它下面一两层。发生这种情况时，定义会被**无名提取并被静默丢弃**。`name_field` 告诉 parser 去哪里找。

每个候选按顺序尝试，分两遍解析：

1. **先 field**——通过该 tree-sitter field 名称访问的 child。Fields 会在任何类型搜索之前跨*所有*候选尝试，因此精确的 field 总是胜过更宽泛的匹配。
2. **类型化后代**——如果没有候选匹配 field，则取第一个 *node type* 等于某候选的后代（有界深度）。这覆盖了位于无 field 包装器之下的名称。

解析出的 node 随后被下钻到它第一个承载文本的叶子并清理（剥离周围的 `{}`/引号/空白；拒绝多行或过大的文本）。因为解析锚定在你配置的候选上，它永远不会抓取无关的内部 identifier。

```toml
[languages.bibtex]
extensions = [".bib"]
grammar = "bibtex"
class_node_types = ["entry"]
name_field = ["key"]            # @article{smith2020,...} -> "smith2020"

[languages.latex]
extensions = [".tex"]
grammar = "latex"
class_node_types = ["section", "chapter", "subsection"]
function_node_types = ["new_command_definition"]
name_field = ["name", "text", "declaration"]
#   \section{Introduction}   -> "Introduction" (via `text`)
#   \newcommand{\foo}{bar}    -> "\foo"        (via `declaration`)

[languages.markdown]
extensions = [".md"]
grammar = "markdown"
class_node_types = ["section"]
name_field = ["inline"]         # "# My Heading" -> "My Heading" (typed descendant)
```

当 grammar 的 node types 把名称放在不同位置时，使用**列表**（LaTeX 的 `section` 用 `text`，`\newcommand` 用 `declaration`）：第一个能解析的候选胜出。省略 `name_field` 则完全保留之前的行为。

## 找到正确的 node type 名称

Node type 名称因 grammar 而异，所以你需要看看 grammar 实际产生的树。两个简单选项：

**选项 1——tree-sitter playground。** 把一个片段粘贴到 <https://tree-sitter.github.io/tree-sitter/7-playground.html>，从解析树读出 node 名称（先选择匹配的 grammar）。

**选项 2——用 Python 本地探测。** 你的 build 使用的确切 grammar 版本就是 `tree_sitter_language_pack` 中的那个，所以本地探测是最可靠的真相来源：

```bash
uv run python - <<'EOF'
import tree_sitter_language_pack as tslp

source = b"""
-module(math_utils).
add(A, B) -> helper(A) + B.
helper(X) -> X * 2.
"""

def dump(node, depth=0):
    print("  " * depth + node.type, node.text.decode()[:40].replace("\n", " "))
    for child in node.children:
        dump(child, depth + 1)

dump(tslp.get_parser("erlang").parse(source).root_node)
EOF
```

选择包裹整个定义（`function_clause`，而非内部的 `atom`）和整个 call 表达式（`call`，而非被调用 identifier）的 node types。

## 完整示例：Erlang 端到端

`src/math_utils.erl`：

```erlang
-module(math_utils).
-export([add/2, scale/2]).
-import(lists, [map/2]).

-record(point, {x, y}).

add(A, B) ->
    helper(A) + B.

helper(X) -> X * 2.

scale(Points, F) ->
    lists:map(fun(P) -> add(P, F) end, Points).
```

使用快速开始中的 `[languages.erlang]` 配置，一次 build 会产生：

- `Function` nodes `add`、`helper`、`scale`（来自 `function_clause`），每个的 `language = "erlang"`。
- 一个 `Class` node `point`（来自 `record_decl`）。
- `CALLS` edges `add → helper` 和 `scale → add`，解析为它们的同文件 qualified names，外加远程调用的 `scale → lists:map`。
- 一条指向 `lists` 的 `IMPORTS_FROM` edge（来自 `import_attribute`）。
- 从文件到每个定义的 `CONTAINS` edges。

## 提取如何工作（及其局限）

自定义语言与内置语言走同一个通用 tree-sitter walker——没有需要维护的每语言代码路径。这保持了功能的简单性，但通用启发式有局限：

- **名称提取使用默认的 name-field 启发式。** Walker 会查找常见 identifier 类型的 child node（`identifier`、`name`、`type_identifier`……），并回退到 grammar 的 `name` field（`node.child_by_field_name("name")`）。把定义名称存在其他形状中的 grammars（例如非标准 field 嵌套两层）会产生无名——因此被跳过——的定义。
- **被调用者提取会探测常见 field 名称**（`function`、`callee`、`expr`、`name`），并下钻穿过 curried applications。古怪的 call 形状可能漏掉。
- **Import targets** 来自 grammar 的 `module`/`name`/`path`/`source` field（若存在），否则记录原始语句文本。
- **没有跨文件 module 解析。** Import edges 保留书写时的 module 名称（例如 `lists`）；不会像拥有专门 resolver 的内置语言那样解析为文件路径。
- **没有语言专属附加功能**：诸如基于 decorator 的 test 检测、framework 注解或 SFC 处理这类功能只存在于内置语言。

如果某个语言需要比通用 walker 能提供的更深支持，请开一个 issue——配置驱动支持是入口，而不是天花板。

## 故障排查

- 启用 `-v`/日志运行一次 build，查找 `languages.toml` 警告——每个被跳过的条目都会精确说明被跳过的原因。
- 探测 grammar 可用性：
  `uv run python -c "import tree_sitter_language_pack as t; t.get_language('erlang')"`
  （如果 grammar 未捆绑，会抛出 `LookupError`。）
- 配置在 parser 被构造时读取（每次 `build`/`update`），因此配置变更在下次 build 时生效——编辑后重新运行 `uv run code-review-graph build`。
