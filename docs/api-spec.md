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
  "status": "ok",
  "timestamp": 1783923171.453,
  "rag_mode": "local_llm",
  "knowledge_dir": "C:\\...\\docs\\knowledge-finance",
  "chunk_count": 87,
  "generation_model": "gemma3:4b-it-qat"
}
```

## POST /api/chat

質問を受け取り、`RAG_MODE` に応じて `mock`、`local`、`local_llm`、`azure` の RAG サービスで回答します。`local_llm` はローカル検索結果だけを根拠として Ollama/Gemma で回答し、引用番号を検証します。生成に失敗した場合は検索原文へ安全に回退します。

### リクエスト

```json
{
  "question": "振込はいつまで取り消せますか。",
  "client_id": "browser-550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "conversation-001"
}
```

### レスポンス

```json
{
  "answer": "受付状態が RECEIVED の場合は取消可能です。[S1]",
  "citations": [
    {
      "title": "03-domestic-transfer-operations.md / FAQ",
      "chunk_id": "03-domestic-transfer-operations-004",
      "content": "RECEIVED の間は取消可能です。..."
    }
  ],
  "retrieved_chunks": [
    {
      "chunk_id": "03-domestic-transfer-operations-004",
      "title": "国内振込の受付と実行 / FAQ",
      "score": 0.3368,
      "content": "RECEIVED の間は取消可能です。..."
    }
  ],
  "latency_ms": 2,
  "rewritten_query": "振込はいつまで取り消せますか。",
  "token_usage": {
    "prompt_tokens": 512,
    "completion_tokens": 32,
    "total_tokens": 544
  },
  "rag_mode": "local_llm",
  "model": "gemma3:4b-it-qat",
  "fallback_used": false,
  "sanitized_question": "振込はいつまで取り消せますか。",
  "memory_usage": {
    "enabled": true,
    "context_items": 2,
    "stored_items": 0,
    "masked_pii": [],
    "dropped_items": 0
  },
  "generation_metrics": {
    "context_chunks": 3,
    "context_characters": 2840,
    "prompt_characters": 3492,
    "model_load_ms": 9210.4,
    "prompt_eval_ms": 8120.7,
    "generation_ms": 21840.3,
    "ollama_total_ms": 39220.8,
    "prompt_tokens_per_second": 18.9,
    "generation_tokens_per_second": 2.15,
    "done_reason": "stop",
    "fallback_reason": "",
    "evidence_completion_used": false
  }
}
```

`client_id` と `conversation_id` は任意です。両方がある場合のみ会話記憶を保存・参照します。質問は PII 清洗後に検索と生成へ渡され、清洗結果を `sanitized_question` で返します。

`generation_metrics` は `local_llm` の生成工程を分解した値です。Ollama が返す nanosecond 指標を ms に変換し、モデルロード、Prompt 評価、Token 生成を個別表示します。回退時は `fallback_reason` に `insufficient_retrieval`、`ollama_unavailable`、`invalid_model_response`、`generation_error` のいずれかが入ります。小型モデルが一文だけで終了し、検索原文から不足条件を決定論的に追加した場合は `evidence_completion_used=true` になります。

## GET /api/memory

`client_id` に紐づく、有効期限内の治理済み記憶を返します。返却項目には `kind`、`key`、マスク済み `value`、`confidence`、`expires_at` が含まれます。

```text
GET /api/memory?client_id=browser-550e8400-e29b-41d4-a716-446655440000
```

## DELETE /api/memory

`conversation_id` を指定した場合はその会話由来の記憶、指定しない場合は `client_id` の全記憶を削除します。

```text
DELETE /api/memory?client_id=...&conversation_id=...
DELETE /api/memory?client_id=...
```

## POST /api/memory/cleanup

有効期限を過ぎた記憶を SQLite から削除します。通常は Chat 処理時にも自動実行されます。

## GET /api/observability

現在のバックエンドプロセスが受け付けた Chat のインメモリ集計と、取得時点の資源状態を返します。

- `metrics`: sample 数、Fallback 率・理由、根拠補完率、平均/P50/P95、平均ロード/Prompt/生成時間、平均生成 tokens/s、直近 10 件
- `resources.system`: CPU 使用率、総/使用可能メモリ
- `resources.backend`: FastAPI プロセスの PID、RSS、CPU 使用率
- `resources.ollama`: Ollama プロセスと `/api/ps` が返す常駐モデル、モデルサイズ、VRAM、Context、失効時刻

この集計は開発用であり、バックエンド再起動時に消えます。

## DELETE /api/observability

インメモリの Chat 性能サンプルだけを削除します。会話記憶、Ollama モデル、ナレッジ索引には影響しません。

## GET /api/search/debug

検索クエリと上位 5 件の Chunk、スコア、原文プレビューを返します。`local`、`local_llm`、`azure` で利用できます。

```text
GET /api/search/debug?q=本人確認書類の住所が異なる場合
```

## POST /api/index/rebuild

`local` と `local_llm` では `KNOWLEDGE_DIR` の Markdown を再読込してインメモリ索引を更新します。`azure` では Azure AI Search の索引定義を作成または更新します。

`local` のレスポンス例：

```json
{
  "status": "ok",
  "message": "ローカルインデックスを再作成しました",
  "chunk_count": 87,
  "knowledge_dir": "C:\\...\\docs\\knowledge-finance"
}
```
