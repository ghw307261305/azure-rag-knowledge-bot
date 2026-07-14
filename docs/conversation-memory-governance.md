# P5 会话记忆治理

## 目标

P5 不是把全部聊天记录原样送回模型，而是在下一次对话前建立一个受治理的记忆层：先清洗和脱敏，再只保存明确、低风险、可过期、可查看、可删除的结构化记忆。

## 数据流程

```mermaid
flowchart LR
    input[用户输入] --> clean[Unicode 与脏数据清洗]
    clean --> pii[PII 脱敏]
    pii --> classify[白名单记忆提取]
    classify --> pref[preference\n90 天]
    classify --> fact[fact\n30 天]
    pref --> db[(本地 SQLite)]
    fact --> db
    db --> context[可信度与有效期过滤]
    context --> prompt[Gemma Prompt\n非权威辅助上下文]
    pii --> retrieval[金融知识库检索]
    retrieval --> prompt
```

## 保存什么

| 类型 | 触发方式 | 默认可信度 | 默认有效期 | 用途 |
|---|---|---:|---:|---|
| `preference` | 明确要求中文/日语/英语、简洁/详细回答 | 0.85–0.90 | 90 天 | 仅调整回答格式 |
| `fact` | 明确使用“请记住：”“覚えておいて”“remember that” | 0.90 | 30 天 | 低风险用户背景辅助 |

系统不会把普通问题自动推断成长期事实，也不会保存原始聊天全文。相同 `client_id + kind + key` 使用 upsert，避免重复和相互冲突的偏好不断累积。

## 不保存什么

- 邮箱、电话、邮编、账号、客户编号、10–19 位长数字
- 包含 PII 占位符的记忆候选
- Prompt Injection、系统提示词提取等 Memory Poisoning 内容
- HTML 标签、控制字符、零宽字符、超长或大量重复字符
- 模型生成的回答或模型自行推断的用户属性

旧版浏览器 `localStorage` 中的问题和回答在加载时也会执行基础 PII 清洗，并覆盖为清洗后的历史记录。

## PII 处理

当前使用确定性规则替换为：

- `[EMAIL]`
- `[PHONE]`
- `[POSTAL_CODE]`
- `[ACCOUNT_NUMBER]`
- `[LONG_NUMBER]`

清洗后的问题用于检索、Gemma 生成、API 的 `sanitized_question` 以及新的浏览器历史。原始 PII 不进入 SQLite 记忆数据库。

## 记忆如何提供给模型

浏览器首次启动时生成匿名 `client_id`，每个聊天会话使用独立 `conversation_id`。同一浏览器的新会话可以读取仍有效的记忆。

记忆在 Prompt 中被标记为 `<governed_memory>`，并遵守以下边界：

- `preference` 只能控制语言和详略程度。
- `fact` 不能成为金融规定、产品条件或业务判断依据。
- 金融知识文档始终优先于会话记忆。
- 会话记忆不能生成 `[S#]` Citation。
- 只有白名单 preference 会转换为格式指令；任意 fact 永远不会提升为 system 指令。

当前 Gemma 3 4B 在“日语问题 + 日语证据”场景中可能继续使用日语，即使存在中文 preference。因此语言 preference 是软约束。P5 不追加第二次翻译调用，以避免双倍延迟和翻译阶段引入事实偏差。

## 用户控制

前端导航栏的 `Memory` 按钮可查看：

- 类型：`preference` / `fact`
- 保存值
- 可信度
- 有效期

用户可以一键删除当前浏览器的全部记忆。删除单个聊天记录时，也会请求删除该会话对应的服务端记忆。

API：

```text
GET    /api/memory?client_id=...
DELETE /api/memory?client_id=...
DELETE /api/memory?client_id=...&conversation_id=...
POST   /api/memory/cleanup
```

## 配置

```dotenv
MEMORY_ENABLED=true
MEMORY_DB_PATH=output/memory/conversation-memory.sqlite3
MEMORY_PREFERENCE_TTL_DAYS=90
MEMORY_FACT_TTL_DAYS=30
MEMORY_MAX_ITEMS=12
```

SQLite 文件属于本地运行数据，已通过 `.gitignore` 排除。

## 验证结果

- PII 清洗与脏数据压缩：通过
- Preference / Fact 分类：通过
- PII 与 Memory Poisoning 不入库：通过
- 可信度、TTL、upsert、过期清理：通过
- 跨会话读取：通过
- 查看、按会话删除、全部删除：通过
- 真实 Gemma 调用：`context_items=2`、`stored_items=0`、`fallback_used=false`
- 删除验证：测试数据 `deleted=2`

## 当前限制

- `client_id` 是浏览器匿名标识，不是登录身份或安全授权边界。
- SQLite 当前未加密，只适合本地 PoC；生产环境需要加密、访问控制与审计。
- 规则式 PII 检测不能覆盖姓名、自然语言地址和所有地区格式。
- 自动提取仅覆盖白名单表达，避免错误记忆；覆盖率低于通用 LLM 抽取。
- 语言和风格偏好最终仍受本地模型指令服从能力影响。
