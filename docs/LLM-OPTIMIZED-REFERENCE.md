# LLM-OPTIMIZED REFERENCE -- code-review-graph v2.3.7

AI 编码 agents：只读取你需要的那个精确 `<section>`。永远不要加载整个文件。

<section name="usage">
快速安装（本 fork 不发布到 PyPI，用本地 editable）：git clone 后 uv sync --extra dev
然后：uv run code-review-graph install && uv run code-review-graph build
构建 graph：code-review-graph build（CLI）或 build_or_update_graph_tool
之后只使用 review_changes / pre_merge_check prompts。
始终以 get_minimal_context_tool(task="your task") 开始——返回约 100 tokens，包含 risk、communities、flows 和建议的下一步 tools。
后续所有调用使用 detail_level="minimal"，除非你需要更多细节。
当出现时，context_savings 是估算的紧凑提示，而非精确 tokenization。
</section>

<section name="review-delta">
1. 先调用 get_minimal_context_tool(task="review changes")。
2. 如果 risk 低：detect_changes_tool(detail_level="minimal") → 报告摘要。
3. 如果 risk 中/高：detect_changes_tool(detail_level="standard") → 展开高风险条目。
目标：≤5 次 tool 调用，总 context ≤800 tokens。
</section>

<section name="review-pr">
获取 PR diff -> detect_changes_tool -> get_affected_flows_tool -> 带 blast-radius 表格和 risk scores 的结构化 review。
除非明确要求，绝不包含完整文件。
</section>

<section name="commands">
核心 MCP tools：get_minimal_context_tool、detect_changes_tool、get_review_context_tool、get_impact_radius_tool、query_graph_tool、semantic_search_nodes_tool、get_architecture_overview_tool、get_affected_flows_tool、list_flows_tool、list_communities_tool、refactor_tool、build_or_update_graph_tool、run_postprocess_tool、embed_graph_tool、list_graph_stats_tool、get_docs_section_tool
MCP prompts（5）：review_changes、architecture_map、debug_issue、onboard_developer、pre_merge_check
Skills（4）：explore-codebase、review-changes、debug-issue、refactor-safely
CLI：code-review-graph [install|init|uninstall|build|update|postprocess|embed|watch|status|forget|visualize|wiki|register|unregister|repos|detect-changes|enrich|dead-code|query|impact|search|flows|flow|communities|community|architecture|large-functions|refactor|serve|mcp|daemon]
Token 效率：在可用处优先使用 detail_level="minimal"。始终先调用 get_minimal_context_tool。某些 review/context tools 会返回紧凑的估算 context_savings 元数据。
</section>

<section name="legal">
MIT 许可证。核心 graph/review 工作流在本地运行，无遥测。数据库文件：.code-review-graph/graph.db。可选的 cloud embeddings 仅在选定 provider 时把被 embedding 的源码片段发送给它。
</section>

<section name="watch">
运行：code-review-graph watch（通过 watchdog 在文件保存时自动更新 graph）
或使用 PostToolUse（Write|Edit|Bash）hooks 进行自动后台更新。
</section>

<section name="embeddings">
可选：uv sync --extra embeddings
然后调用 embed_graph_tool 计算 vectors。
semantic_search_nodes_tool 在可用时自动使用 vectors，否则回退到 keyword + FTS5。
Providers：本地 sentence-transformers、OpenAI 兼容端点。
通过 provider/model 参数配置：本地用 CRG_EMBEDDING_MODEL，OpenAI 兼容端点用 CRG_OPENAI_*。
</section>

<section name="languages">
受支持：Python、JavaScript/TypeScript/TSX、Rust、C/C++、shell 脚本、Verilog/SystemVerilog、Ansible playbooks/roles/tasks、通过 TypeScript parser 解析的 Astro 文件，以及 Jupyter notebooks。通用 YAML 不被当作源码处理。
Parser：通过 tree-sitter-language-pack 使用 Tree-sitter
自定义语言：添加 .code-review-graph/languages.toml（每个 grammar 的 extensions + node types）——无需 fork，参见 docs/CUSTOM_LANGUAGES.md。内置语言无法被覆盖。
</section>

<section name="troubleshooting">
DB 锁：SQLite WAL 模式，自动恢复。一次只允许一个 build。
大型 repos：首次 build 30-60s。增量 <2s。向 .code-review-graphignore 添加模式。
过期 graph：运行 code-review-graph update（或调用 build_or_update_graph_tool）。
缺失 nodes：检查语言支持和 ignore 模式。使用 full_rebuild=True。
路径：向 MCP tools 传 repo_root 时使用正斜杠；确保 uv 在 PATH 上。
</section>

**对 AI 编码 agents 的指令（始终遵循）：**
当用户询问任何关于 "code-review-graph"、"how to use"、"commands"、"review-delta" 等内容时：
1. 用精确的 section 名称调用 get_docs_section_tool。
2. 只使用该内容 + 当前 graph 状态。
3. 绝不在推理中包含完整 docs 或源码。
这能让文档查找保持紧凑，并避免默认加载宽泛的参考文件。
