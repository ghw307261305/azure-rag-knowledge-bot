# 認証設計ドキュメント（Auth Design）

本ドキュメントでは、Azure RAG Knowledge Bot の認証・認可の設計と、環境ごとの切り替え方針を記録します。

---

## 概要：3 層の認証スコープ

| 層 | 対象 | 本 POC の状態 |
|----|------|--------------|
| ① サービス間認証 | バックエンド ↔ Azure OpenAI / AI Search | API Key（ローカル）→ Managed Identity（本番） |
| ② ユーザー認証 | ブラウザ → フロントエンド / API | 未実装（POC スコープ外） |
| ③ API アクセス制御 | POST /api/chat への認可 | 未実装（全リクエスト受け付け） |

---

## ① サービス間認証：環境別の切り替え設計

### ローカル開発環境（APP_ENV=local）

```
ブラウザ → FastAPI（localhost:8000） → Azure OpenAI / AI Search
                                         [API Key 認証]
```

- `.env` ファイルで `AZURE_OPENAI_API_KEY` と `AZURE_SEARCH_API_KEY` を管理
- `.env` は `.gitignore` で除外済み。Git に絶対コミットしない
- `AzureKeyCredential(api_key)` を使用

**コード例（search_service.py）:**
```python
from azure.core.credentials import AzureKeyCredential
credential = AzureKeyCredential(settings.azure_search_api_key)
```

---

### Azure 本番環境（APP_ENV=production）

```
ブラウザ → Static Web Apps → App Service（Managed Identity）→ Azure OpenAI / AI Search
                                                               [RBAC ロール認証]
```

- App Service に **システム割り当てマネージド ID** を有効化
- Azure OpenAI に `Cognitive Services OpenAI User` ロールを付与
- Azure AI Search に `Search Index Data Reader` ロールを付与
- コードは `DefaultAzureCredential` に切り替え（環境を意識せず認証）

**切り替え手順（コード変更）:**

```python
# 現在（API Key）
from azure.core.credentials import AzureKeyCredential
credential = AzureKeyCredential(settings.azure_search_api_key)

# 本番移行後（Managed Identity）
from azure.identity import DefaultAzureCredential
credential = DefaultAzureCredential()
```

**本番移行チェックリスト:**
1. [ ] App Service → ID → システム割り当て → 状態: オン
2. [ ] Azure OpenAI → アクセス制御(IAM) → `Cognitive Services OpenAI User` をマネージド ID に付与
3. [ ] Azure AI Search → アクセス制御(IAM) → `Search Index Data Reader` をマネージド ID に付与
4. [ ] `AzureKeyCredential` を `DefaultAzureCredential` に置換
5. [ ] App Service の環境変数から API Key を削除

---

## ② ユーザー認証（未実装・設計のみ）

### 採用方針：Microsoft Entra ID + MSAL

```
ブラウザ ─(Entra ID ログイン)→ ID Token 取得
      ↓
Static Web Apps（SWA 組み込み認証）
      ↓ Authorization Bearer Token
App Service（JWT 検証）
```

**実装イメージ（フロントエンド）:**

```typescript
import { PublicClientApplication } from "@azure/msal-browser";

const msalInstance = new PublicClientApplication({
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID,
    authority: "https://login.microsoftonline.com/{tenant_id}",
  }
});

// ログイン
await msalInstance.loginPopup({ scopes: ["openid", "profile"] });

// API 呼び出し時にトークンを付与
const token = await msalInstance.acquireTokenSilent({ scopes: [apiScope] });
fetch("/api/chat", {
  headers: { Authorization: `Bearer ${token.accessToken}` }
});
```

**実装イメージ（バックエンド）:**

```python
from fastapi.security import OAuth2AuthorizationCodeBearer
from jose import jwt

oauth2_scheme = OAuth2AuthorizationCodeBearer(...)

@router.post("/api/chat")
async def chat(request: ChatRequest, token: str = Depends(oauth2_scheme)):
    # JWT 検証（Entra ID 公開鍵で検証）
    payload = jwt.decode(token, public_key, algorithms=["RS256"])
    user_id = payload["sub"]
    ...
```

---

## ③ API アクセス制御（未実装・設計のみ）

### レート制限（slowapi）

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/api/chat")
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    ...
```

### IP 許可リスト（企業内利用時）

```python
ALLOWED_IPS = os.getenv("ALLOWED_IPS", "").split(",")

@app.middleware("http")
async def ip_filter(request: Request, call_next):
    client_ip = request.client.host
    if ALLOWED_IPS and client_ip not in ALLOWED_IPS:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)
```

---

## 設定値の管理方針

| 環境 | 管理場所 | 手法 |
|------|---------|------|
| ローカル | `.env` ファイル | dotenv（git 除外） |
| Azure App Service | アプリケーション設定 | Azure Portal / Bicep パラメータ |
| GitHub Actions | Repository Secrets | `${{ secrets.XXX }}` |
| 本番移行後 | Managed Identity | キー不要 |

### GitHub Secrets 設定一覧

| Secret 名 | 値の取得元 | 用途 |
|-----------|-----------|------|
| `AZURE_WEBAPP_NAME` | App Service のリソース名 | デプロイ先の指定 |
| `AZURE_WEBAPP_PUBLISH_PROFILE` | Azure Portal → App Service → 発行プロファイルのダウンロード | バックエンドデプロイ認証 |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Azure Portal → Static Web Apps → デプロイトークン | フロントエンドデプロイ認証 |
| `VITE_API_BASE_URL` | `https://{App Service名}.azurewebsites.net/api` | フロントエンドのビルド時 API URL |

---

## 将来の認証ロードマップ

```
Phase 1（現在）: API Key + CORS 制限
Phase 2（近期）: Managed Identity（サービス間キーレス化）
Phase 3（中期）: Entra ID（ユーザー認証）
Phase 4（長期）: RBAC（ドキュメント権限、部門別アクセス制御）
```
