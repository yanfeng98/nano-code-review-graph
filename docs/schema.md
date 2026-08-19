# 知识图谱 Schema

## Node 类型

### File
表示一个源码文件。

| 属性 | 类型 | 描述 |
|------|------|------|
| name | string | 绝对文件路径 |
| file_path | string | 对 File nodes 与 name 相同 |
| language | string | 检测到的语言（python、typescript 等） |
| line_start | int | 始终为 1 |
| line_end | int | 总行数 |
| file_hash | string | 文件内容的 SHA-256（用于变更检测） |

### Class
表示 class、struct、interface、enum 或 module 定义。

| 属性 | 类型 | 描述 |
|------|------|------|
| name | string | Class 名称 |
| file_path | string | 包含该 class 的文件 |
| line_start | int | 定义起始行 |
| line_end | int | 定义结束行 |
| language | string | 源语言 |
| parent_name | string? | 包围它的 class（用于嵌套 classes） |
| modifiers | string? | 访问修饰符（public、abstract 等） |

### Function
表示 function、method 或 constructor 定义。

| 属性 | 类型 | 描述 |
|------|------|------|
| name | string | 函数名称 |
| file_path | string | 包含该函数的文件 |
| line_start | int | 定义起始行 |
| line_end | int | 定义结束行 |
| language | string | 源语言 |
| parent_name | string? | 包围它的 class（用于 methods） |
| params | string? | 作为源码文本的参数列表 |
| return_type | string? | 返回类型注解 |
| is_test | bool | 是否为一个 test 函数 |

### Test
与 Function 相同的 schema，但 `kind = "Test"` 且 `is_test = true`。识别依据：
- 名称以 `test_` 或 `Test` 开头
- 名称以 `_test` 或 `_spec` 结尾
- 文件匹配 test 文件模式（`test_*.py`、`*.test.ts` 等）
- 语言特定的 test markers（如支持的情况下，常见的 Rust test attributes）

### Type
表示 type alias、interface、enum、struct 式类型，或语言暴露出来的 parser 特定 type 构造。

| 属性 | 类型 | 描述 |
|------|------|------|
| name | string | Type 名称 |
| file_path | string | 包含该 type 的文件 |
| line_start | int | 定义起始行 |
| line_end | int | 定义结束行 |

## Edge 类型

### CALLS
一个函数调用另一个函数。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 调用者的 qualified name |
| target | string | 被调用函数的名称（可能未限定） |
| file_path | string | 调用发生的文件 |
| line | int | 调用的行号 |

### IMPORTS_FROM
一个文件从另一个模块或文件导入。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 导入方文件路径 |
| target | string | 被导入的 module/path |
| file_path | string | 与 source 相同 |
| line | int | import 的行号 |

### INHERITS
一个 class 继承自另一个 class。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 子 class 的 qualified name |
| target | string | 父 class 名称 |
| file_path | string | 包含子 class 的文件 |

### IMPLEMENTS
一个 class 实现一个 interface（TypeScript）。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 实现该 interface 的 class |
| target | string | Interface 名称 |

### CONTAINS
结构性包含：一个文件包含一个 class，一个 class 包含一个 method。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 容器（文件路径或 class qualified name） |
| target | string | 被包含 node 的 qualified name |

### TESTED_BY
一个函数被一个 test 函数测试。

| 属性 | 类型 | 描述 |
|------|------|------|
| source | string | 被测试的函数 |
| target | string | Test 函数的 qualified name |

### DEPENDS_ON
通用依赖关系（用于非特定依赖）。

### REFERENCES
对另一个 symbol 的值级引用，常用于 function-as-value 模式，例如回调映射、数组或赋值。

### INJECTS
用于被注入字段和构造器参数的依赖注入关系（保留 edge kind；当前无生产者）。

### CONSUMES / PRODUCES
当某个源消费或产出命名资源时，由专门的 parsers 发出的数据或事件流关系（保留 edge kinds；当前无生产者）。

## Qualified Name 格式

Nodes 由 qualified names 唯一标识：

```
# 文件 node
/absolute/path/to/file.py

# 顶层函数
/absolute/path/to/file.py::function_name

# 类中的方法
/absolute/path/to/file.py::ClassName.method_name

# 嵌套类方法
/absolute/path/to/file.py::OuterClass.InnerClass.method_name
```

## SQLite 表

```sql
-- Nodes 表
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    language TEXT,
    parent_name TEXT,
    params TEXT,
    return_type TEXT,
    modifiers TEXT,
    is_test INTEGER DEFAULT 0,
    file_hash TEXT,
    extra TEXT DEFAULT '{}',
    community_id INTEGER,
    updated_at REAL NOT NULL,
    signature TEXT
);

-- Edges 表
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_qualified TEXT NOT NULL,
    target_qualified TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER DEFAULT 0,
    extra TEXT DEFAULT '{}',
    confidence REAL DEFAULT 1.0,
    confidence_tier TEXT DEFAULT 'EXTRACTED',
    updated_at REAL NOT NULL
);

-- Metadata 表
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Flows 表（v2.0）
CREATE TABLE flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entry_point_id INTEGER NOT NULL,
    depth INTEGER NOT NULL,
    node_count INTEGER NOT NULL,
    file_count INTEGER NOT NULL,
    criticality REAL NOT NULL DEFAULT 0.0,
    path_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Flow memberships 表（v2.0）
CREATE TABLE flow_memberships (
    flow_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (flow_id, node_id)
);

-- Communities 表（v2.0）
CREATE TABLE communities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    parent_id INTEGER,
    cohesion REAL NOT NULL DEFAULT 0.0,
    size INTEGER NOT NULL DEFAULT 0,
    dominant_language TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Full-text search 虚拟表（v2.0）
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    name, qualified_name, file_path, signature,
    content='nodes', content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Token 高效摘要表（v6）
CREATE TABLE community_summaries (
    community_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT DEFAULT '',
    key_symbols TEXT DEFAULT '[]',
    risk TEXT DEFAULT 'unknown',
    size INTEGER DEFAULT 0,
    dominant_language TEXT DEFAULT ''
);

CREATE TABLE flow_snapshots (
    flow_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    entry_point TEXT NOT NULL,
    critical_path TEXT DEFAULT '[]',
    criticality REAL DEFAULT 0.0,
    node_count INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0
);

CREATE TABLE risk_index (
    node_id INTEGER PRIMARY KEY,
    qualified_name TEXT NOT NULL,
    risk_score REAL DEFAULT 0.0,
    caller_count INTEGER DEFAULT 0,
    test_coverage TEXT DEFAULT 'unknown',
    security_relevant INTEGER DEFAULT 0,
    last_computed TEXT DEFAULT ''
);

-- Embeddings 表，存储在 embeddings 数据库中
CREATE TABLE embeddings (
    qualified_name TEXT PRIMARY KEY,
    vector BLOB NOT NULL,
    text_hash TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown'
);
```

索引包括 qualified-name、file-path、node-kind、edge source/target/kind、community、flow criticality、risk score、复合 edge 查找索引，以及复合 edge upsert 索引。
