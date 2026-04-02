# 外部API連携ガイド

## 概要
本システムが連携する外部サービスおよびAPI仕様の概要を説明します。

## 連携サービス一覧

| サービス | 用途 | 認証方式 | 環境 |
|---------|------|---------|------|
| Azure OpenAI | 回答生成・Embedding | API Key / Managed Identity | dev / prod |
| Azure AI Search | ドキュメント検索 | API Key / Managed Identity | dev / prod |
| SendGrid | メール送信 | API Key | dev / prod |
| Stripe | 決済処理 | Secret Key | dev / prod |
| Google Analytics | アクセス解析 | Measurement Protocol | prod のみ |

## Azure OpenAI 連携

### エンドポイント
```
https://{resource_name}.openai.azure.com/
```

### 主な利用API

**Chat Completions（回答生成）**
```
POST /openai/deployments/{deployment_name}/chat/completions?api-version=2024-02-01
```

**Embeddings（ベクトル化）**
```
POST /openai/deployments/{embedding_deployment}/embeddings?api-version=2024-02-01
```

### レート制限
- TPM（Tokens Per Minute）: デプロイメント設定に依存
- RPM（Requests Per Minute）: 60〜1000（ティアによる）
- 429エラー時はExponential Backoff（初期待機1秒、最大8秒）

## Azure AI Search 連携

### エンドポイント
```
https://{service_name}.search.windows.net
```

### 主な利用API

**ドキュメント検索**
```
POST /indexes/{index_name}/docs/search?api-version=2024-07-01
```

**ドキュメント追加/更新**
```
POST /indexes/{index_name}/docs/index?api-version=2024-07-01
```

### ハイブリッド検索のリクエスト例
```json
{
  "search": "学校ユーザー 求人削除",
  "vectorQueries": [
    {
      "kind": "vector",
      "vector": [0.1, 0.2, ...],
      "fields": "content_vector",
      "k": 5
    }
  ],
  "select": "chunk_id,title,section,source,content",
  "top": 5
}
```

## SendGrid 連携

### 利用目的
- ユーザー登録確認メール
- パスワードリセットメール
- 面接通知メール
- システム障害通知

### 送信制限
- 1日あたり最大10,000通（プランによる）
- バウンス率が5%を超えるとアカウントが停止リスク

### メールテンプレート管理
- テンプレートはSendGrid管理画面で管理
- テンプレートIDをアプリの環境変数で管理

## Stripe 連携

### 利用目的
- 学校ユーザーの月額・年額課金
- プランアップグレード時の日割り請求
- 請求書の自動発行

### Webhook イベント
- `invoice.payment_succeeded` → 支払い確認、プラン有効化
- `invoice.payment_failed` → 支払い失敗通知、督促メール
- `customer.subscription.deleted` → 解約処理

### セキュリティ
- Webhook署名検証を必須実装（`Stripe-Signature`ヘッダ）
- Secret KeyはAzure Key Vault or App Service環境変数で管理

## 共通エラーハンドリング方針

| HTTPステータス | 対応 |
|-------------|------|
| 429 | Retry-Afterヘッダを参照、なければExponential Backoff |
| 500/503 | 3回リトライ後に失敗ログ記録・アラート送信 |
| 401/403 | リトライ不可、即時エラー処理 |

## 関連ドキュメント
- api-error-code-guide.md
- incident-response-procedure.md
