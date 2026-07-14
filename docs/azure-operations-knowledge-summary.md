# Azure 操作知识总整理

## 范围

本文把当前仓库中和 Azure 相关的知识集中整理，优先以代码、脚本、Bicep 为准，文档中的未来规划会单独说明。

## 1. 当前涉及的 Azure 服务

- Azure OpenAI
  - 用途：query rewrite、embedding、最终回答生成
- Azure AI Search
  - 用途：知识索引、hybrid search
- App Service / App Service Plan
  - 用途：Bicep 里的标准 PaaS 承载方案
- Azure VM
  - 用途：`infra/scripts/deploy-vm.ps1` 里的 VM + nginx + systemd 部署方案
- Azure Monitor / Application Insights
  - 用途：监控、告警、排障
- Managed Identity / Entra ID / Key Vault
  - 用途：安全与认证
  - 状态：主要还是规划中

## 2. 当前命名和区域

- Resource Group: `rg-rag-demo-dev`
- Azure OpenAI: `aoai-rag-demo-dev`
- Azure AI Search: `srch-rag-demo-dev`
- Search Index: `knowledge-index`
- region: `japaneast`
- Bicep 默认 appName: `rag-demo-dev`
- Bicep 默认资源名
  - App Service Plan: `asp-rag-demo-dev`
  - Backend App: `app-rag-demo-dev-backend`
  - Frontend App: `app-rag-demo-dev-frontend`

## 3. 当前系统里的 Azure 调用链路

在线问答链路已经实际接入 Azure：

1. 前端调用 `POST /api/chat`
2. 后端做基础 prompt injection 检查
3. Azure OpenAI 重写查询
4. Azure OpenAI 生成查询 embedding
5. Azure AI Search 执行 hybrid search
6. 后端按分数阈值决定 fallback 或继续
7. Azure OpenAI 基于检索上下文生成最终回答

当前后端 API：

- `GET /api/health`
- `POST /api/chat`
- `GET /api/search/debug`
- `POST /api/index/rebuild`

注意：`/api/index/rebuild` 当前只执行 `create_index()`，不做完整重建。

## 4. 当前 Azure OpenAI 实现

代码位置：`backend/app/services/openai_service.py`

- SDK：`openai.AzureOpenAI`
- API version：`2024-06-01`
- Chat deployment：`AZURE_OPENAI_CHAT_DEPLOYMENT`
- Embedding deployment：`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

当前职责：

- `rewrite_query(question)`
- `get_embedding(text)`
- `generate_answer(question, context)`

## 5. 当前 Azure AI Search 实现

代码位置：`backend/app/services/search_service.py`

当前索引字段：

- `chunk_id`
- `title`
- `section`
- `source`
- `content`
- `content_vector`

当前向量检索配置：

- HNSW
- profile: `hnsw-profile`
- vector dimension: `3072`

当前搜索方式：

- keyword search + vector search
- Azure AI Search 用 RRF 合并结果

## 6. 当前索引构建知识

代码位置：

- 构建脚本：`backend/scripts/build_index.py`
- 分块逻辑：`backend/app/services/chunking_service.py`
- 知识源：`docs/knowledge/*.md`

实际流程：

1. 读取全部 Markdown 知识文档
2. 按 `##` 二级标题优先切分
3. 为每个 chunk 生成 metadata
4. 调 Azure OpenAI 生成 embedding
5. 调 Azure AI Search 创建或更新索引
6. 批量上传文档

当前可执行命令：

```bash
cd backend
python scripts/build_index.py
python scripts/build_index.py --rebuild
```

实际含义：

- 普通执行：遍历并重新上传全部文档，不是真正意义上的差分更新
- `--rebuild`：删除索引后全量重建

## 7. 当前环境变量知识

后端实际读取：

- `APP_ENV`
- `LOG_LEVEL`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_SEARCH_INDEX_NAME`
- `TOP_K`
- `MAX_CHUNKS`

前端相关：

- `VITE_API_BASE_URL`

示例环境文件现状：

- 仓库中有 `.env`
- 仓库中有 `.env copy.example`
- README 提到 `.env.example`，但实际文件名不是这个

## 8. 当前认证与安全状态

代码真实状态：

- Azure OpenAI 走 API Key
- Azure AI Search 走 `AzureKeyCredential`
- 还没有切换到 `DefaultAzureCredential()`

文档目标状态：

- local：API Key 或本地 Azure 登录
- dev/staging/prod：Managed Identity
- 用户登录：Entra ID + MSAL
- 高安全场景：Key Vault + Managed Identity

当前已经明确的安全边界：

- 前端不直接持有 Azure 密钥
- Azure 调用都在 backend
- `.env` 不应提交
- CORS 通过 `CORS_ORIGIN` 补充 Azure 前端域名

## 9. 当前部署知识

### 路线 A：Bicep + App Service

`infra/bicep/main.bicep` 会部署：

- Linux App Service Plan
- Backend App Service
- Frontend App Service

Backend App Service 注入：

- `APP_ENV=production`
- `AZURE_OPENAI_*`
- `AZURE_SEARCH_*`
- `TOP_K=5`
- `MAX_CHUNKS=5`
- `CORS_ORIGIN`

### 路线 B：Azure VM + nginx

`infra/scripts/deploy-vm.ps1` 的流程是：

1. 本地构建 frontend
2. 生成 `.env.production`
3. 上传 backend、docs、frontend dist、env 文件
4. VM 上安装 `nginx`、`python3-venv`
5. 建立 `azure-rag-backend.service`
6. nginx 反代 `/api`
7. 用 `/api/health` 验证部署

### 路线 C：文档里的 App Service + Static Web Apps

文档里还记录了：

- Backend 用 App Service
- Frontend 用 Static Web Apps
- 发布命令包括 `az webapp deploy`、slot swap、SWA deploy

结论：当前仓库存在多条 Azure 部署路径，尚未完全收敛为单一标准。

## 10. 当前运维知识

排障入口：

- `GET /api/health`
- Azure Portal
- Application Insights
- Azure Monitor
- `/api/search/debug`

文档中的常见排查顺序：

1. 看 App Service 状态和扩缩容
2. 看 Azure OpenAI throttling / rate limit
3. 看 Azure AI Search 索引状态
4. 必要时重启应用

发布后验证点：

- `/api/health` 返回 200
- 主流程可用
- RAG 检索/回答可用
- Application Insights 无明显错误率升高

## 11. 需要特别注意的差异点

### 11.1 索引维度文档和代码不一致

- 文档 `docs/knowledge/search-index-maintenance.md` 写 `1536`
- 代码实际是 `3072`

应以代码为准。

### 11.2 索引脚本命令文档和代码不一致

- 文档写 `--mode update` / `--mode rebuild`
- 代码实际支持 `--rebuild`

应以脚本代码为准。

### 11.3 `/api/index/rebuild` 名称和行为不一致

- 名称像完整重建
- 实际只会创建/更新索引结构，不会重算 embedding，不会重新上传文档

### 11.4 部署方案尚未统一

当前同时存在：

- Frontend on App Service
- Frontend on Static Web Apps
- Frontend on VM + nginx

### 11.5 认证设计和代码实现尚未统一

- 文档大量写 Managed Identity / Entra ID
- 代码当前还是 API Key

## 12. 当前状态的一句话结论

这个项目已经完成 Azure OpenAI + Azure AI Search 的核心接入，具备问答链路、索引链路和 Azure 部署脚本；但部署标准、认证方式、索引维护说明和部分文档内容还没有完全收敛，后续在 Azure 上继续操作时应优先以代码和脚本的真实行为为准。
