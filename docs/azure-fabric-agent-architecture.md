# Azure Fabric + AI Search + VM Agent Chatbot 実装アーキテクチャ図

本ドキュメントは、Microsoft Azure を基盤とした企業向け AI Agent Chatbot の実装アーキテクチャを示します。  
デプロイ方針は Azure VM / Azure VMSS を中心とし、アプリケーション実行レイヤーでは Nginx、React 静的フロントエンド、FastAPI Chat API、Agent Router、Tool Gateway を稼働させます。ナレッジ検索は Azure AI Search、レポート分析は Microsoft Fabric と Power BI Semantic Model が担当します。

## 1. 全体実装アーキテクチャ図

```mermaid
flowchart TB
    classDef user fill:#F7F3E8,stroke:#8A6A2F,color:#1F2933,stroke-width:1px
    classDef edge fill:#FFF3E0,stroke:#D97706,color:#1F2933,stroke-width:1px
    classDef app fill:#EEF5F7,stroke:#2F6B7B,color:#1F2933,stroke-width:1px
    classDef ai fill:#EAF2FF,stroke:#4A6FB3,color:#1F2933,stroke-width:1px
    classDef data fill:#F2F4F7,stroke:#667085,color:#1F2933,stroke-width:1px
    classDef security fill:#FCE7F3,stroke:#BE185D,color:#1F2933,stroke-width:1px
    classDef monitor fill:#ECFDF3,stroke:#027A48,color:#1F2933,stroke-width:1px

    user["業務ユーザー<br/>Web / Teams / 企業ポータル"]:::user
    admin["管理者 / データエンジニア"]:::user

    subgraph Entry["入口・認証レイヤー"]
        entra["Microsoft Entra ID<br/>SSO / MFA / ユーザーグループ"]:::security
        appgw["Application Gateway<br/>WAF / TLS / ルーティング"]:::edge
    end

    subgraph Runtime["Azure VMSS アプリ実行レイヤー"]
        nginx["Nginx<br/>React 静的フロントエンド<br/>リバースプロキシ"]:::app
        api["FastAPI Chat API<br/>/api/chat /api/health"]:::app
        router["Agent Router<br/>意図判定 / ツール選択"]:::app
        gateway["Tool Gateway<br/>Search / Fabric / Action Tools"]:::app
        session["セッション・監査モジュール<br/>Session / Trace / Feedback"]:::app
    end

    subgraph AgentAI["AI Agent・モデルレイヤー"]
        foundry["Azure AI Foundry<br/>Agent Service / Tool Calling"]:::ai
        aoai["Azure OpenAI<br/>Chat / Embedding / Query Rewrite"]:::ai
        safety["Azure AI Content Safety<br/>入出力安全チェック"]:::ai
    end

    subgraph SearchLayer["ナレッジ検索レイヤー"]
        blob["Azure Blob Storage / OneLake Files<br/>PDF / Word / Markdown / FAQ"]:::data
        indexer["文書処理・インデックス作成ジョブ<br/>Parse / Chunk / Metadata / Embedding"]:::app
        search["Azure AI Search<br/>Hybrid Search / Vector Search<br/>Semantic Ranker / Citations"]:::ai
    end

    subgraph FabricLayer["レポート・データ分析レイヤー"]
        sources["業務システムデータソース<br/>ERP / CRM / SQL / Excel / API"]:::data
        onelake["Microsoft Fabric OneLake"]:::data
        lakehouse["Fabric Lakehouse / Warehouse<br/>Bronze / Silver / Gold"]:::data
        semantic["Power BI Semantic Model<br/>認定指標 / RLS / DAX"]:::data
        fabricAgent["Fabric Data Agent<br/>自然言語による構造化データQA"]:::ai
        reports["Power BI Reports<br/>レポートリンク / 可視化ページ"]:::data
    end

    subgraph Platform["セキュリティ・運用基盤"]
        mi["Managed Identity<br/>サービス間のパスワードレスアクセス"]:::security
        kv["Azure Key Vault<br/>キー / 証明書 / 設定"]:::security
        pe["Private Endpoint / VNet<br/>閉域ネットワークアクセス"]:::security
        appinsights["Application Insights<br/>Trace / Latency / Dependency"]:::monitor
        logs["Log Analytics / Azure Monitor<br/>ログ / アラート / ワークブック"]:::monitor
    end

    user --> entra
    user --> appgw
    entra -. "OIDC / JWT" .-> api
    appgw --> nginx
    nginx --> api
    api --> safety
    api --> router
    router --> gateway
    router --> session

    gateway --> foundry
    gateway --> aoai
    gateway --> search
    gateway --> fabricAgent
    gateway --> semantic
    gateway --> reports

    admin --> blob
    blob --> indexer
    indexer --> aoai
    indexer --> search

    sources --> onelake
    onelake --> lakehouse
    lakehouse --> semantic
    semantic --> reports
    semantic --> fabricAgent

    mi -. "パスワードレスアクセス" .-> aoai
    mi -. "パスワードレスアクセス" .-> search
    mi -. "パスワードレスアクセス" .-> kv
    mi -. "パスワードレスアクセス" .-> semantic
    pe -. "プライベートアクセス" .-> aoai
    pe -. "プライベートアクセス" .-> search
    pe -. "プライベートアクセス" .-> blob

    api --> appinsights
    router --> appinsights
    session --> logs
    appinsights --> logs
```

この図は、次の 3 つの実装上の問いに答えます。

- アプリケーションの配置先：React 静的フロントエンド、FastAPI API、Agent Router、Tool Gateway は Azure VM / Azure VMSS 上で稼働します。
- 文書ナレッジの検索方法：業務文書を Blob Storage または OneLake Files に格納し、解析、分割、ベクトル化を行ったうえで Azure AI Search に登録します。
- レポートデータの分析方法：業務データを Microsoft Fabric OneLake、Lakehouse/Warehouse、Power BI Semantic Model に集約し、Agent が Fabric Data Agent、SQL、DAX、Power BI API を呼び出して分析結果を生成します。

## 2. ナレッジ検索 / RAG フロー図

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant FE as React Chat UI
    participant API as FastAPI Chat API
    participant R as Agent Router
    participant OAI as Azure OpenAI
    participant AIS as Azure AI Search
    participant Log as Application Insights

    U->>FE: ナレッジ系の質問を入力
    FE->>API: POST /api/chat
    API->>R: question, user, session を渡す
    R->>OAI: Query Rewrite
    OAI-->>R: 検索最適化済み query
    R->>OAI: Embedding を生成
    OAI-->>R: query vector
    R->>AIS: Hybrid Search<br/>keyword + vector + filters
    AIS-->>R: 候補 chunks
    R->>AIS: Semantic Ranker で再ランク付け
    AIS-->>R: Top chunks + scores + metadata
    R->>R: 関連度しきい値を判定<br/>grounded context を組み立て
    alt 信頼できる根拠あり
        R->>OAI: context に基づいて回答生成
        OAI-->>R: answer + token usage
        R-->>API: answer + citations + retrieved_chunks
    else 信頼できる根拠なし
        R-->>API: fallback answer + empty citations
    end
    API->>Log: latency, tokens, search score を記録
    API-->>FE: ChatResponse
    FE-->>U: 回答、引用元、デバッグ情報を表示
```

オフラインのインデックス作成フローは、制御されたバッチ処理として実行します。業務文書を Blob Storage または OneLake Files に格納し、文書解析、OCR、chunk 分割、metadata 付与、embedding 生成を行ったうえで、Azure AI Search Index に登録します。インデックスには少なくとも `content`、`content_vector`、`source`、`section`、`securityGroups` を保持し、引用表示と文書単位の権限制御を実現します。

## 3. Fabric レポート分析フロー図

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant FE as React Chat UI
    participant API as FastAPI Chat API
    participant R as Agent Router
    participant TG as Tool Gateway
    participant FD as Fabric Data Agent
    participant SM as Power BI Semantic Model
    participant WH as Fabric Lakehouse / Warehouse
    participant OAI as Azure OpenAI

    U->>FE: レポートまたは指標分析の質問を入力
    FE->>API: POST /api/chat
    API->>R: question, user, session を渡す
    R->>R: 意図をレポート分析として判定
    R->>TG: Fabric ツールを選択
    TG->>SM: 指標カタログと権限を確認<br/>RLS / workspace role
    SM-->>TG: 利用可能な指標、ディメンション、期間
    TG->>FD: 自然言語を構造化クエリへ変換
    FD-->>TG: SQL / DAX / クエリ計画
    TG->>WH: SQL 実行または Gold データセット読込
    WH-->>TG: 明細または集計結果
    TG->>SM: DAX 実行または認定指標読込
    SM-->>TG: 指標結果
    TG->>OAI: トレンド説明、異常サマリー、要因仮説を生成
    OAI-->>TG: 分析テキスト
    TG-->>R: 指標値 + 分析説明 + reportUrl
    R-->>API: answer + metricResult + reportLink
    API-->>FE: ChatResponse
    FE-->>U: レポート説明、主要指標、Power BI リンクを表示
```

Fabric へのデータ取り込みは、標準的なレイクハウス分層で設計します。業務システムのデータを Fabric Data Factory、Pipeline、Mirroring のいずれかで OneLake に取り込み、Bronze、Silver、Gold の各層で整備します。その後、Power BI Semantic Model に公開し、Chatbot は認定指標、レポートリンク、権限制御済みのクエリ結果のみを参照します。

## 4. 実装境界とデフォルト方針

- VM / VMSS はアプリケーション実行基盤として利用し、大規模モデルの学習や推論は行いません。モデル推論には Azure OpenAI または Azure AI Foundry を使用します。
- Azure AI Search は非構造化ナレッジ検索を担当します。インデックスには `content`、`content_vector`、`source`、`section`、`securityGroups` などの項目を保持し、引用表示と権限制御に利用します。
- Microsoft Fabric は構造化データの管理、レイクハウスモデリング、指標定義、Power BI レポートを担当します。Agent が計算式を推測するのではなく、Semantic Model 内の認定指標を優先して利用します。
- Tool Gateway は Agent のツール呼び出しを制御されたインターフェースに集約し、モデルが基盤データベース、検索インデックス、レポートサービスへ直接アクセスしないようにします。
- 本番環境では、Entra ID、Managed Identity、Key Vault、Private Endpoint、Application Insights、Log Analytics を標準で有効化します。

## 5. 受け入れ確認

- 3 つの Mermaid 図が VS Code Markdown Preview または Mermaid Preview でレンダリングできること。
- メイン経路が「ユーザー -> Application Gateway/WAF -> Azure VMSS -> FastAPI Agent Orchestrator -> Azure OpenAI/Foundry + Azure AI Search + Microsoft Fabric」として明確に表現されていること。
- 文書ナレッジ検索の経路が「Blob Storage/OneLake -> Parse -> Chunk -> Embedding -> Azure AI Search -> citations」として明確に表現されていること。
- レポート分析の経路が「Fabric OneLake -> Lakehouse/Warehouse -> Power BI Semantic Model -> Fabric Data Agent / DAX / SQL -> Chatbot の分析回答」として明確に表現されていること。
- 文書全体が UTF-8 で保存され、文字化けがないこと。
