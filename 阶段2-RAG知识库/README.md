# 阶段 2：RAG 知识库

目标：构建可检索、可引用、可评测的企业知识库问答系统。

学习范围：

- PDF、Word、网页、Markdown 和 Excel 解析
- 文档清洗、切分和增量更新
- Embedding、向量数据库和 Metadata Filter
- Hybrid Search、Rerank 和 Query Rewrite
- 引用来源、权限控制和多租户
- RAG 召回率、准确率和幻觉评测

## 开发环境准备：Docker 安装 PostgreSQL + PGVector

本阶段使用 PostgreSQL 保存业务数据，并使用 PGVector 保存文档向量。ECS 已安装 Docker 的情况下，可以直接使用 Docker Compose 启动数据库。


-[项目代码](https://github.com/caoshuyuan88-dev/hello-rag-langchain.git)