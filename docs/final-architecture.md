# 最終成果物 システムアーキテクチャ図

本ドキュメントは Azure RAG Knowledge Bot の現在の Demo から最終本番環境への完全なシステムアーキテクチャを記述します。

---

## 1. 最終全体アーキテクチャ図

```mermaid
flowchart TB
    subgraph Users["ユーザー層"]
        browser["🖥️ ブラウザ"]
        admin["🔧 管理者"]
    end

    subgraph CDN["グローバル配信"]
        afd["Azure Front Door<br/>CDN + WAF + グローバル負荷分散"]
    end

    subgraph Auth["認証層"]
        entra["Microsoft Entra ID<br/>(Azure AD)<br/>OAuth 2.0 / OIDC"]
    end

    subgraph Frontend["フロントエンド層"]
        swa["Azure Static Web Apps<br/>React + TypeScript<br/>MSAL 認証統合"]
    end

    subgraph Backend["バックエンド層 (App Service / Container Apps)"]
        apim["Azure API Management<br/>レート制限 · 認証 · ログ · バージョン管理"]
        subgraph AppService["Azure App Service (Linux)"]
            fastapi["FastAPI Application"]
            subgraph Services["サービス層"]
                routes["API Routes<br/>/chat · /search · /health<br/>/admin · /feedback"]
                rag["RAG Orchestrator<br/>オーケストレーション · 閾値 · リトライ"]
                oai_svc["OpenAI Service<br/>Query Rewrite<br/>Embedding<br/>Answer Generation"]
                search_svc["Search Service<br/>Hybrid Search<br/>Index Management"]
                session_svc["Session Service<br/>マルチターン対話 · コンテキスト管理"]
                auth_svc["Auth Middleware<br/>JWT 検証 · RBAC"]
                content_safety["Content Safety<br/>Prompt Injection 検出<br/>入出力フィルタリング"]
            end
        end
    end

    subgraph AzureAI["Azure AI サービス層"]
        aoai["Azure OpenAI Service<br/>GPT-4o (Chat/Rewrite)<br/>text-embedding-3-large"]
        ais["Azure AI Search<br/>Hybrid Search (Keyword + Vector)<br/>RRF 融合 · Semantic Ranker"]
        aics["Azure AI Content Safety<br/>有害コンテンツ検出<br/>Prompt Injection 防御"]
    end

    subgraph Data["データ層"]
        cosmos["Azure Cosmos DB<br/>会話履歴 · ユーザー設定<br/>クエリログ · フィードバック記録"]
        blob["Azure Blob Storage<br/>ナレッジドキュメント原本<br/>(Markdown / PDF / Word)"]
        redis["Azure Cache for Redis<br/>セッションキャッシュ · ホットクエリキャッシュ"]
    end

    subgraph Pipeline["ナレッジパイプライン (オフライン)"]
        github_repo["GitHub Repository<br/>ナレッジドキュメントバージョン管理"]
        gh_actions["GitHub Actions<br/>CI/CD · 自動インデックストリガー"]
        indexer["Index Builder<br/>ドキュメント解析 · チャンク分割 · Embedding<br/>Blue-Green インデックス切替"]
    end

    subgraph Observability["オブザーバビリティ"]
        appinsights["Azure Application Insights<br/>分散トレーシング · パフォーマンス監視"]
        loganalytics["Azure Log Analytics<br/>構造化ログ · アラート"]
        dashboard["Azure Dashboard / Grafana<br/>KPI ダッシュボード · リアルタイム監視"]
    end

    subgraph Security["セキュリティ基盤"]
        keyvault["Azure Key Vault<br/>鍵管理 · 証明書"]
        mi["Managed Identity<br/>キーレスサービス間認証"]
        vnet["Azure VNet + Private Endpoint<br/>ネットワーク分離"]
    end

    %% ユーザートラフィック経路
    browser --> afd
    afd --> swa
    afd --> apim
    browser --> entra
    entra --> swa
    swa --> apim
    apim --> fastapi

    %% バックエンド内部
    fastapi --> routes
    routes --> auth_svc
    routes --> content_safety
    routes --> rag
    rag --> oai_svc
    rag --> search_svc
    rag --> session_svc

    %% Azure AI 呼び出し
    oai_svc --> aoai
    search_svc --> ais
    content_safety --> aics

    %% データ層
    session_svc --> cosmos
    session_svc --> redis
    rag --> cosmos
    routes --> cosmos

    %% ナレッジパイプライン
    admin --> github_repo
    github_repo --> gh_actions
    gh_actions --> indexer
    indexer --> blob
    indexer --> aoai
    indexer --> ais
    blob --> indexer

    %% セキュリティ
    mi --> aoai
    mi --> ais
    mi --> cosmos
    mi --> keyvault
    keyvault --> fastapi
    vnet --> aoai
    vnet --> ais
    vnet --> cosmos

    %% オブザーバビリティ
    fastapi --> appinsights
    apim --> appinsights
    appinsights --> loganalytics
    loganalytics --> dashboard
```

---

## 2. オンライン質疑応答フロー（最終版）

```mermaid
sequenceDiagram
    participant U as ユーザーブラウザ
    participant AFD as Azure Front Door
    participant Entra as Microsoft Entra ID
    participant SWA as Static Web Apps
    participant APIM as API Management
    participant API as FastAPI
    participant Auth as Auth Middleware
    participant Safety as Content Safety
    participant RAG as RAG Orchestrator
    participant Redis as Redis Cache
    participant OAI as Azure OpenAI
    participant AIS as Azure AI Search
    participant Cosmos as Cosmos DB
    participant AI as App Insights

    U->>Entra: ① ログイン (MSAL)
    Entra-->>U: ID Token + Access Token
    U->>AFD: ② 質問送信 (Bearer Token)
    AFD->>APIM: WAF フィルタリング + ルーティング
    APIM->>APIM: レート制限チェック · API バージョンルーティング
    APIM->>API: リクエスト転送
    API->>Auth: ③ JWT 検証 + RBAC
    Auth-->>API: user_id, roles
    API->>Safety: ④ Prompt Injection 検出
    Safety->>Safety: Azure AI Content Safety
    Safety-->>API: 安全確認完了

    API->>RAG: ⑤ answer(question, user_id, session_id)
    RAG->>Redis: キャッシュ確認
    alt キャッシュヒット
        Redis-->>RAG: cached answer
    else キャッシュミス
        RAG->>Cosmos: 会話履歴読み込み (マルチターンコンテキスト)
        Cosmos-->>RAG: conversation context
        RAG->>OAI: ⑥ rewrite_query(question + context)
        OAI-->>RAG: rewritten_query
        RAG->>OAI: ⑦ get_embedding(rewritten_query)
        OAI-->>RAG: query_vector
        RAG->>AIS: ⑧ hybrid_search + semantic_ranker
        AIS-->>RAG: retrieved_chunks (with RRF scores)
        RAG->>RAG: ⑨ スコア閾値判定 + コンテキスト組み立て
        alt 十分な関連結果あり
            RAG->>OAI: ⑩ generate_answer(question, context, history)
            OAI-->>RAG: answer + token_usage
        else 関連結果なし
            RAG-->>RAG: fallback answer
        end
        RAG->>Redis: キャッシュ書き込み
    end

    RAG->>Cosmos: ⑪ 会話記録 + クエリログ保存
    RAG-->>API: ChatResponse
    API->>AI: ⑫ トレーシングデータ記録 (latency, tokens, scores)
    API-->>APIM: Response
    APIM-->>AFD: Response
    AFD-->>U: answer + citations + debug info
```

---

## 3. ナレッジパイプラインアーキテクチャ（オフラインインデックス）

```mermaid
flowchart TD
    subgraph Source["ナレッジソース"]
        md["Markdown ドキュメント"]
        pdf["PDF ドキュメント"]
        word["Word ドキュメント"]
        api_doc["API ドキュメント"]
    end

    subgraph VCS["バージョン管理"]
        repo["GitHub Repository<br/>docs/knowledge/"]
        pr["Pull Request<br/>ドキュメントレビュー"]
    end

    subgraph CICD["CI/CD Pipeline"]
        trigger["GitHub Actions Trigger<br/>(push / schedule / manual)"]
        validate["ドキュメント検証<br/>フォーマット · 内容チェック"]
    end

    subgraph Processing["ドキュメント処理"]
        parse["ドキュメントパーサー<br/>Markdown / PDF / Word"]
        chunk["インテリジェントチャンク分割<br/>## 見出し分割<br/>+ 固定長 fallback"]
        meta["メタデータ抽出<br/>title · section · source<br/>created_at · updated_at"]
        embed["Embedding 生成<br/>text-embedding-3-large<br/>3072 次元"]
    end

    subgraph Indexing["インデックスデプロイ (Blue-Green)"]
        idx_new["新インデックス作成<br/>knowledge-index-v{N+1}"]
        upload["バッチアップロード<br/>100 docs/batch"]
        verify["インデックス検証<br/>サンプルクエリ · 品質チェック"]
        swap["エイリアス切替<br/>knowledge-index → v{N+1}"]
        cleanup["旧インデックスクリーンアップ<br/>直近 2 バージョン保持"]
    end

    subgraph Target["ターゲットサービス"]
        ais["Azure AI Search<br/>Hybrid Index"]
        blob["Azure Blob Storage<br/>原本アーカイブ"]
    end

    Source --> repo
    repo --> pr --> trigger
    trigger --> validate
    validate --> parse
    parse --> chunk
    chunk --> meta
    meta --> embed
    embed --> idx_new
    idx_new --> upload
    upload --> verify
    verify -->|合格| swap
    verify -->|失敗| trigger
    swap --> cleanup
    upload --> ais
    parse --> blob
```

---

## 4. セキュリティアーキテクチャ

```mermaid
flowchart LR
    subgraph External["外部"]
        user["ユーザー"]
        attacker["潜在的攻撃者"]
    end

    subgraph Edge["エッジ防御"]
        waf["Azure Front Door WAF<br/>DDoS 防御 · IP 制限<br/>Bot 検出"]
    end

    subgraph AuthN["認証"]
        entra["Microsoft Entra ID<br/>OAuth 2.0 / OIDC<br/>MFA 対応"]
    end

    subgraph Gateway["API ゲートウェイ"]
        apim["API Management<br/>レート制限 (10 req/min)<br/>JWT 検証<br/>API バージョン管理<br/>リクエストログ"]
    end

    subgraph App["アプリケーション層防御"]
        csrf["CORS ポリシー"]
        injection["Prompt Injection 防御<br/>Azure AI Content Safety"]
        rbac["RBAC 権限制御<br/>部門別ドキュメント権限"]
        sanitize["入力サニタイズ<br/>出力フィルタリング"]
    end

    subgraph Infra["インフラセキュリティ"]
        vnet["VNet + Private Endpoint<br/>内部ネットワーク通信"]
        mi["Managed Identity<br/>キーレス認証"]
        kv["Key Vault<br/>鍵ローテーション"]
        tls["TLS 1.2+<br/>エンドツーエンド暗号化"]
    end

    subgraph Monitor["セキュリティ監視"]
        sentinel["Microsoft Sentinel<br/>脅威検出"]
        alerts["セキュリティアラート<br/>異常アクセス通知"]
    end

    user --> waf
    attacker --> waf
    waf --> entra
    entra --> apim
    apim --> csrf
    csrf --> injection
    injection --> rbac
    rbac --> sanitize
    sanitize --> vnet
    vnet --> mi
    mi --> kv

    apim --> sentinel
    injection --> alerts
```

---

## 5. オブザーバビリティアーキテクチャ

```mermaid
flowchart TD
    subgraph Sources["データソース"]
        api_logs["API リクエストログ<br/>レイテンシ · ステータスコード · ユーザー"]
        rag_logs["RAG パイプラインログ<br/>Rewrite · Search · Generate"]
        token_logs["Token 使用量<br/>prompt · completion · total"]
        search_logs["検索品質ログ<br/>スコア · ヒット数 · 空結果率"]
        error_logs["エラーログ<br/>例外 · タイムアウト · レート制限"]
        feedback["ユーザーフィードバック<br/>👍/👎 · コメント"]
    end

    subgraph Collection["収集層"]
        otel["OpenTelemetry SDK<br/>構造化ログ · Trace · Metrics"]
    end

    subgraph Storage["ストレージ・分析"]
        appinsights["Application Insights<br/>分散トレーシング<br/>依存関係マップ"]
        loganalytics["Log Analytics Workspace<br/>KQL クエリ"]
        cosmos_log["Cosmos DB<br/>クエリログ · フィードバックデータ"]
    end

    subgraph Visualization["可視化 + アラート"]
        dashboard["Azure Dashboard<br/>リアルタイム KPI"]
        workbook["Azure Workbook<br/>週次レポート · トレンド分析"]
        alerts["Azure Monitor Alerts<br/>P95 レイテンシ > 5s<br/>エラー率 > 5%<br/>空結果率 > 30%"]
    end

    Sources --> otel
    otel --> appinsights
    otel --> loganalytics
    feedback --> cosmos_log
    search_logs --> cosmos_log
    appinsights --> dashboard
    loganalytics --> workbook
    loganalytics --> alerts
    cosmos_log --> workbook
```

---

## 6. デプロイアーキテクチャ

```mermaid
flowchart LR
    subgraph Dev["開発環境"]
        local["ローカル開発<br/>localhost:8000 + 5173<br/>API Key 認証"]
    end

    subgraph CI["CI/CD"]
        gh["GitHub Actions"]
        test["自動テスト<br/>ユニットテスト · 結合テスト"]
        build_fe["フロントエンドビルド<br/>npm build"]
        build_be["バックエンドパッケージ<br/>Python zip deploy"]
        bicep["Bicep デプロイ<br/>Infrastructure as Code"]
    end

    subgraph Staging["ステージング環境"]
        stg_fe["Static Web Apps<br/>(staging slot)"]
        stg_be["App Service<br/>(staging slot)"]
        stg_test["E2E テスト<br/>スモークテスト"]
    end

    subgraph Production["本番環境"]
        prod_fe["Static Web Apps<br/>(production)"]
        prod_be["App Service<br/>(production)<br/>auto-scale"]
        prod_swap["Slot Swap<br/>ゼロダウンタイムデプロイ"]
    end

    Dev --> gh
    gh --> test
    test --> build_fe
    test --> build_be
    build_fe --> stg_fe
    build_be --> stg_be
    bicep --> Staging
    stg_fe --> stg_test
    stg_be --> stg_test
    stg_test -->|合格| prod_swap
    prod_swap --> prod_fe
    prod_swap --> prod_be
```

---

## 7. Demo → 最終成果物 対照表

| 項目 | 現在の Demo | 最終成果物 |
|------|-----------|----------|
| **フロントエンドホスティング** | localhost:5173 (Vite dev) | Azure Static Web Apps + Front Door CDN |
| **バックエンドホスティング** | localhost:8000 (Uvicorn) | Azure App Service (auto-scale) + API Management |
| **認証** | なし | Microsoft Entra ID + MSAL + JWT |
| **サービス間認証** | API Key (.env) | Managed Identity (キーレス) |
| **セッション管理** | ブラウザ localStorage | Cosmos DB + Redis Cache |
| **対話能力** | シングルターン質疑応答 | マルチターン対話 (コンテキスト記憶) |
| **コンテンツ安全性** | 基本キーワードマッチング | Azure AI Content Safety |
| **レート制限** | なし | API Management + slowapi |
| **ナレッジソース** | Markdown のみ | Markdown + PDF + Word |
| **インデックス更新** | 手動 build_index.py | GitHub Actions 自動トリガー + Blue-Green デプロイ |
| **ログ** | プレーンテキスト print | OpenTelemetry → Application Insights |
| **監視** | なし | Dashboard + アラート + 週次レポート |
| **ネットワークセキュリティ** | パブリックアクセス | VNet + Private Endpoint |
| **CI/CD** | 手動デプロイ | GitHub Actions + Staging Slot + Swap |
| **鍵管理** | .env ファイル | Azure Key Vault |
| **検索強化** | Hybrid Search (RRF) | + Semantic Ranker |
| **ユーザーフィードバック** | なし | 👍/👎 フィードバック → 品質分析クローズドループ |

---

## 8. Azure リソース一覧（最終成果物）

| リソース | SKU / ティア | 用途 |
|---------|-----------|------|
| Azure Front Door | Standard | CDN + WAF + グローバルルーティング |
| Azure Static Web Apps | Standard | フロントエンドホスティング |
| Azure App Service | B2+ (auto-scale) | バックエンド API |
| Azure API Management | Consumption / Basic | API ゲートウェイ |
| Azure OpenAI Service | S0 | GPT-4o + Embedding |
| Azure AI Search | Basic+ | ハイブリッド検索 + Semantic Ranker |
| Azure AI Content Safety | S0 | コンテンツ安全フィルタリング |
| Azure Cosmos DB | Serverless | セッション · ログ · フィードバック |
| Azure Cache for Redis | Basic | キャッシュ |
| Azure Blob Storage | Hot | ナレッジドキュメントアーカイブ |
| Azure Key Vault | Standard | 鍵管理 |
| Azure Application Insights | — | APM + トレーシング |
| Azure Log Analytics | — | ログ分析 |
| Azure Monitor | — | アラート |
| Microsoft Entra ID | — | ID 認証 |
| GitHub Actions | — | CI/CD |
