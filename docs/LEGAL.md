# 法律与隐私

**许可证：** MIT（见项目根目录的 [LICENSE](../LICENSE)）

**隐私：**
- 零遥测
- 所有 graph 数据本地存储在 `.code-review-graph/graph.db`
- 核心 graph build、review、search 和 CLI/MCP 工作流在本地运行
- 可选的本地 embeddings 首次使用时可能从 HuggingFace 下载 sentence-transformers 模型
- 可选的 cloud embedding providers（`openai`）仅在显式选择时把被 embedding 的源码片段发送给配置的 provider
- 远程 embedding providers 除非设置 `CRG_ACCEPT_CLOUD_EMBEDDINGS=1`，否则会打印 egress 警告
- Streamable HTTP MCP transport 默认绑定到 localhost

**数据：** 核心 graph 数据留在你的机器上。如果你选择使用 cloud embedding provider，被 embedding 的文本会在该 provider 的条款下离开你的机器。

**保证：** 按现状提供，不附带任何形式的保证。
