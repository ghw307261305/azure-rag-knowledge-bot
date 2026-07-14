# Azure RAG Knowledge Bot

Azure OpenAI と Azure AI Search を利用する RAG チャットボット PoC です。
固定結果を返す `mock`、ローカル文書を実検索する `local`、Ollama/Gemma で回答を生成する `local_llm`、Azure の実サービスを利用する `azure` を切り替えられます。クラウド環境がなくても、実際の金融ナレッジを使った検索、生成、引用表示、Fallback を確認できます。

## 現在の到達点

- `backend/` に FastAPI ベースの API と RAG オーケストレーションを実装
- `frontend/` に React + TypeScript + Vite のチャット UI を実装
- `mock` モードでは固定の回答、引用、検索片を Azure 非接続で返却
- `local` モードでは `docs/knowledge-finance/` を文字 n-gram TF-IDF で検索し、金融業務の原文と引用を返却
- 架空の SFB を想定した 26 文書・142 Chunk に、商品コード、手数料、限度額、受付時間、承認人数、例外フローを収録
- `local_llm` モードでは同じ検索結果を Ollama の `gemma3:4b-it-qat` に渡し、根拠番号付き回答を生成
- 生成結果の引用番号を検証し、Ollama 停止・空回答・不正引用時は検索原文へ安全に回退
- P4 の生成評価セットは 22 問で、Groundedness、Citation、数値根拠、拒答、Prompt Injection を自動評価
- P5 では会話記憶を PII 清洗し、preference / fact、信頼度、TTL を分離してローカル SQLite に保存
- Memory 画面と API から記憶の確認、会話単位削除、全削除が可能
- 質問単位の記憶 ON/OFF、単一記憶削除、認証ユーザー所有権を実装
- Azure 非依存の短期 JWT、user / operator / admin、金融文書 ACL Filter を実装
- 回答ごとの 👍 / 👎 と任意理由を PII 清洗後にローカル保存
- P6 では Gemma の Context / Token / Thread / Batch / 常駐時間を調整し、生成工程別の性能指標と Fallback 理由を可視化
- `/api/observability` から遅延分布、生成速度、モデル常駐状態、CPU・メモリ使用量を確認可能
- Request ID、JSON 構造化ログ、Prometheus endpoint、任意の OTLP Trace 出力を実装
- P6 最終評価は 22 / 22 合格。実務回答、拒答、安全入力をローカル Gemma で再評価済み
- `azure` モードでは Query Rewrite、Embedding、Hybrid Search、回答生成を実行
- `KNOWLEDGE_DIR` の Markdown を分割して Azure AI Search に登録するスクリプトを実装
- ブラウザのローカルストレージによる会話履歴と開発用デバッグ表示を実装
- Backend / Frontend / Bicep / 品質評価を確認する CI と統合検証スクリプトを実装

## 技術スタック

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI, Pydantic
- Local LLM: Ollama, Gemma 3 4B IT QAT
- Local Memory: SQLite, deterministic PII sanitization
- Azure Services: Azure OpenAI, Azure AI Search

## RAG 実行モード

`.env` の `RAG_MODE` で実行先を選択します。

| モード | 用途 | Azure 接続 |
|---|---|---|
| `mock` | ローカル開発、自動テスト、画面デモ | 不要 |
| `local` | Markdown ナレッジの実検索、引用、Fallback 検証 | 不要 |
| `local_llm` | Markdown 実検索 + Ollama/Gemma の根拠付き回答生成 | 不要 |
| `azure` | Azure OpenAI / Azure AI Search を使う実 RAG | 必要 |

未指定時は安全のため `mock` が選択されます。`local` と `local_llm` では `/api/search/debug` と `/api/index/rebuild` もローカル索引に対して動作します。

## リポジトリ構成

```text
.
├─ frontend/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ models/
│  │  ├─ prompts/
│  │  ├─ services/
│  │  └─ utils/
│  └─ tests/
├─ docs/
│  ├─ knowledge/
│  ├─ knowledge-finance/
│  ├─ architecture.md
│  ├─ api-spec.md
│  ├─ review-checklist.md
│  └─ known-issues.md
└─ infra/
   ├─ bicep/
   └─ observability/
```

## 環境設定

最初にサンプル設定をコピーします。

```powershell
Copy-Item .env.example .env
```

Azure に接続しない場合は、初期値の `RAG_MODE=local_llm` で実文書検索と Gemma の回答生成を利用できます。事前に Ollama を起動し、`ollama pull gemma3:4b-it-qat` を実行してください。生成モデルを使わず検索だけ確認する場合は `local`、固定レスポンスなら `mock`、Azure を使う場合は `azure` に変更します。

初期の金融ナレッジは `KNOWLEDGE_DIR=docs/knowledge-finance` です。以前の採用業務サンプルへ戻す場合は `KNOWLEDGE_DIR=docs/knowledge` に変更してサービスを再起動してください。金融ナレッジは架空組織の PoC・研修用であり、実在商品の条件や法的助言ではありません。

Azure リソースの命名規約は次のとおりです。

- Resource Group: `rg-rag-demo-dev`
- Azure OpenAI: `aoai-rag-demo-dev`
- Azure AI Search: `srch-rag-demo-dev`
- Search Index: `knowledge-index`

必要な環境変数は [`.env.example`](/c:/rigelsoft/workspace/azure-rag-knowledge-bot/.env.example) を参照してください。

## セットアップ

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

確認先:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/docs`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

確認先:

- `http://127.0.0.1:5173`

### ローカルモデルのスクリーンショット確認

Ollama と Backend の起動後、`/api/health` の `rag_mode` が `local_llm`、`knowledge_dir` が `docs/knowledge-finance` であることを確認します。ナレッジ更新後は Backend を再起動してローカル索引を再構築します。

スクリーンショットには次の質問を使用します。

```text
SFB ダイレクトで50万円を他行へ振り込む場合、手数料と当日扱いの締切、注意事項を教えてください。
```

画面上で次を確認します。

- 通常手数料 `275 円`
- 当日扱いの基準 `平日 15:00 まで`
- 優遇、追加認証、受取金融機関による例外説明
- Citation に `18-transfer-fees-limits-and-service-hours.md`
- `local_llm` と利用モデル名の表示
- 👍 / 👎 の Feedback 操作

この質問は、商品条件、具体的な数値、例外条件、引用元を一画面で示せるため、ケース説明資料のスクリーンショットに適しています。

### テスト

```powershell
cd backend
.venv\Scripts\activate
pytest
```

Frontend のテストと production build：

```powershell
cd frontend
npm test
npm run build
```

Backend、検索品質、Frontend、Bicep をまとめて確認する場合：

```powershell
.\scripts\verify.ps1
```

### 金融ナレッジ検索評価

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_retrieval.py
```

88 問の固定評価セットに対して Hit@K、MRR、Fallback、Answerability、証拠キーワード、検索時間を計測し、`output/evaluation/` に JSON / Markdown レポートを出力します。品質ゲート未達の場合は終了コード 1 になります。詳細は [`docs/retrieval-evaluation.md`](docs/retrieval-evaluation.md) を参照してください。

### ローカル生成回答評価

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py
```

14 問の金融回答、4 問の拒答、4 問の安全入力に対して、期待文書、引用番号、段落引用率、根拠概念、数値根拠、Fallback、Prompt Injection 拒否を評価します。2026-07-14 にローカル Gemma で全 22 問を再実行し、22 / 22 合格を確認しました。詳細は [`docs/generation-evaluation.md`](docs/generation-evaluation.md) を参照してください。

### 会話記憶ガバナンス

ブラウザは匿名 `client_id` と会話 ID を API に送り、バックエンドは質問を清洗してから Gemma と記憶層へ渡します。記憶には明示的 preference / fact だけを保存し、PII、Prompt Injection、原始会話全文は保存しません。詳細は [`docs/conversation-memory-governance.md`](docs/conversation-memory-governance.md) を参照してください。

画面の `Memory ON / OFF` で質問単位の記憶利用を停止でき、Memory 画面から単一項目または全項目を削除できます。

### ローカル認証・文書 ACL

Azure Entra ID が利用できない期間は、`AUTH_MODE=local_jwt` で短期 JWT を使えます。`LOCAL_JWT_SECRET` を 32 文字以上に変更後、次のコマンドで Token を作成します。

```powershell
cd backend
.venv\Scripts\python.exe scripts\create_local_token.py `
  --subject local-user-001 --role operator --group finance-all
```

Frontend から利用する場合は `VITE_LOCAL_AUTH_TOKEN` に Token を設定します。文書 ACL は `docs/knowledge-finance/access-control.json` で管理し、認証時だけ検索結果へ適用します。

### Docker でのローカル起動

Azure や Ollama を使わない検索モードで起動します。

```powershell
docker compose up --build
```

- UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`

Collector、Prometheus、Grafana も起動する場合：

```powershell
$env:OTEL_ENABLED='true'
docker compose --profile observability up --build
```

### P6 ローカル LLM 性能評価

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\benchmark_local_llm.py --runs 2 --cold-start
```

冷启动とモデル常驻後の実リクエストを計測し、ロード、Prompt 評価、生成時間、tokens/s、Fallback、根拠補完を `output/performance/` に保存します。実行中の集計と資源状態は `GET /api/observability` で確認できます。詳細は [`docs/performance-observability.md`](docs/performance-observability.md) を参照してください。

## 現在の主な制限

- ローカル JWT は Entra ID の代替ではなく、Managed Identity と実ユーザー認証は未検証
- CI はテスト・Build・静的検証までで、Azure への自動デプロイは未有効化
- CPU のみで動作する 4B モデルのため、GPU 利用時の速度には到達しない
- Chat 集計は単一バックエンドプロセスのメモリ内データで、再起動時に消える
- 未見質問、実利用ログ、人手レビューを含む外部評価セット
- 匿名 `client_id` を使う PoC 設計であり、記憶 DB の認証・暗号化は未実装
- 氏名や自由形式住所など、規則だけでは検出できない PII

## 次のステップ

- GPU または小型モデルとの A/B ベンチマークを実施
- 実運用向け Dashboard、Alert、Trace 保存期間を定義
- Entra ID と暗号化ストレージを使ったユーザー単位の記憶アクセス制御を追加
- 未見会話ログによる PII 検出率と Memory Poisoning 回帰評価を追加
- Azure 接続環境で End-to-End 検証を実施
