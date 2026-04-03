# Azure RAG Knowledge Bot

Azure OpenAI と Azure AI Search を前提にした、ローカル優先の RAG チャットボット Day 1 骨格です。  
Day 1 では Azure 実接続は行わず、FastAPI と React/TypeScript のローカル実行、モック回答フロー、知識文書サンプルの整備までを対象にしています。

## Day 1 の到達点

- `backend/` に FastAPI ベースの API 骨格を用意
- `frontend/` に React + TypeScript + Vite のチャット UI を用意
- `/api/chat` はモックの回答、引用、検索片を返却
- `docs/knowledge/` に日文の業務知識サンプル文書を配置
- Azure 向けの環境変数契約と命名方針のみ定義

## 技術スタック

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI, Pydantic
- Planned Azure Services: Azure OpenAI, Azure AI Search

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
│  ├─ architecture.md
│  ├─ api-spec.md
│  ├─ review-checklist.md
│  └─ known-issues.md
└─ infra/
   ├─ bicep/
   └─ github-actions/
```

## Azure 準備方針

Day 1 では Azure リソースを実作成しません。後続実装のため、以下の命名規約だけ先に固定します。

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

### テスト

```powershell
cd backend
.venv\Scripts\activate
pytest
```

## Day 1 のスコープ外

- Azure OpenAI / Azure AI Search への実接続
- 文書 chunking、embedding、indexing
- 認証認可、Managed Identity、Entra ID
- CI/CD、Azure へのデプロイ
- 多輪会話、会話履歴保存

## 次のステップ

- Day 2 で文書投入スクリプトを追加
- Azure AI Search のインデックス設計を追加
- `/api/chat` を実際の検索結果と結合

