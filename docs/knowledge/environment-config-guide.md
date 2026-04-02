# 環境設定・構成管理ガイド

## 概要
本ドキュメントでは、ローカル開発・検証・本番環境の構成管理と環境変数の扱い方を定義します。

## 環境一覧

| 環境名 | 用途 | デプロイ先 |
|-------|------|---------|
| local | 開発者ローカル | localhost |
| dev | 開発チーム共有 | Azure（開発用リソース） |
| staging | リリース前検証 | Azure（検証用リソース） |
| production | 本番サービス | Azure（本番リソース） |

## 環境変数一覧

### Azure OpenAI

| 変数名 | 説明 | ローカルでの扱い |
|-------|------|--------------|
| AZURE_OPENAI_ENDPOINT | Azure OpenAI リソースのエンドポイントURL | .env に記載 |
| AZURE_OPENAI_API_KEY | API キー | .env に記載（gitには含めない） |
| AZURE_OPENAI_CHAT_DEPLOYMENT | チャット用デプロイメント名 | .env に記載 |
| AZURE_OPENAI_EMBEDDING_DEPLOYMENT | Embedding用デプロイメント名 | .env に記載 |

### Azure AI Search

| 変数名 | 説明 | ローカルでの扱い |
|-------|------|--------------|
| AZURE_SEARCH_ENDPOINT | Azure AI Search エンドポイントURL | .env に記載 |
| AZURE_SEARCH_API_KEY | 管理者APIキー | .env に記載（gitには含めない） |
| AZURE_SEARCH_INDEX_NAME | 検索インデックス名 | .env に記載 |

### アプリケーション設定

| 変数名 | デフォルト値 | 説明 |
|-------|------------|------|
| APP_ENV | local | 動作環境（local/dev/staging/production） |
| LOG_LEVEL | INFO | ログレベル（DEBUG/INFO/WARNING/ERROR） |
| TOP_K | 5 | 検索で取得するチャンク数 |
| MAX_CHUNKS | 5 | プロンプトに含めるチャンク数の上限 |
| ALLOWED_ORIGINS | http://localhost:5173 | CORS許可オリジン |

## 認証方式の環境別切り替え

### ローカル開発環境
- Azure OpenAI / AI Search は API Key 認証
- `.env` ファイルに直接記載
- `.env` はgitignoreで除外

### Azure 上（dev/staging/production）
- **Managed Identity（推奨）**: パスワードレス認証
  - App Service のシステム割り当てマネージド ID を有効化
  - Azure OpenAI / AI Search に `Cognitive Services User` / `Search Index Data Contributor` ロールを付与
  - コードでは `DefaultAzureCredential()` を使用（API Key 不要）
- **API Key（フォールバック）**: App Service の環境変数に設定

### DefaultAzureCredential の動作順序
```
1. 環境変数（AZURE_CLIENT_ID 等）
2. Workload Identity
3. Managed Identity
4. Visual Studio Code の認証情報
5. Azure CLI の認証情報
6. Azure PowerShell の認証情報
```

ローカルでは `az login` 済みであれば5番目で認証が通る。

## シークレット管理

### してはいけないこと
- `.env` ファイルを git にコミットする
- ソースコードに API Key をハードコードする
- ログにシークレット情報を出力する

### 推奨する方法
- ローカル: `.env` ファイル（.gitignoreに追加済み）
- Azure 環境: App Service の「構成」 > 「アプリケーション設定」
- 高セキュリティが必要な場合: Azure Key Vault + Managed Identity

## フロントエンドの環境変数

Vite では `VITE_` プレフィックスの変数のみビルドに埋め込まれる。

| 変数名 | 説明 |
|-------|------|
| VITE_API_BASE_URL | バックエンドAPIのベースURL |

**注意**: フロントエンドの環境変数はブラウザから見えるため、シークレット情報（API Key等）を含めてはいけない。

## 環境別の .env ファイル構成

```
backend/
  .env          ← ローカル用（gitignore済み）
  .env.example  ← テンプレート（gitに含める）
```

Azure 環境では .env ファイルは使わず、App Service の設定から注入する。

## 関連ドキュメント
- release-deployment-process.md
- onboarding-handover-checklist.md
