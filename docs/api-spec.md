# API 仕様

## GET /

API の起動確認用です。

### レスポンス例

```json
{
  "message": "Azure RAG Knowledge Bot API is running in local"
}
```

## GET /api/health

ヘルスチェック用 API です。

### レスポンス例

```json
{
  "status": "ok"
}
```

## POST /api/chat

質問を受け取り、Day 1 ではモック回答を返却します。

### リクエスト

```json
{
  "question": "学校ユーザーは公開求人を削除できますか。"
}
```

### レスポンス

```json
{
  "answer": "モック回答です。質問「...」に対して、Day 1 では固定の検索結果を根拠として返しています。",
  "citations": [
    {
      "title": "job-posting-rule.md",
      "chunk_id": "job-posting-rule-001",
      "content": "学校ユーザーが公開求人を登録するには..."
    }
  ],
  "retrieved_chunks": [
    {
      "chunk_id": "job-posting-rule-001",
      "title": "job-posting-rule.md",
      "score": 0.98,
      "content": "学校ユーザーが公開求人を登録するには..."
    }
  ],
  "latency_ms": 120
}
```

