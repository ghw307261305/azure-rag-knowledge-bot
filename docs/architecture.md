# アーキテクチャ概要

## 目的

本システムは、Azure OpenAI と Azure AI Search を利用する RAG チャットボットの Day 1 ローカル骨格です。  
この段階では Azure 実接続を行わず、UI、API、知識文書、環境変数契約を先に整備します。

## コンポーネント

- Frontend: React + TypeScript + Vite
- Backend: FastAPI
- Knowledge Source: `docs/knowledge/` 配下の Markdown 文書
- Planned Azure Services:
  - Azure OpenAI
  - Azure AI Search

## Day 1 の処理フロー

1. ユーザーがフロントエンドから質問を送信する
2. フロントエンドが `POST /api/chat` を呼び出す
3. FastAPI がモックの検索結果と引用を組み立てる
4. 回答、引用元、検索片、レイテンシを返却する
5. フロントエンドが回答と引用元を描画する

## 後続設計の前提

- Day 2 以降で Markdown 文書を chunk 化して Azure AI Search に投入する
- Day 3 以降で Azure OpenAI を使った回答生成に置き換える
- 本番を想定した認証認可は将来的に Entra ID / Managed Identity を検討する

## Azure 命名方針

- Resource Group: `rg-rag-demo-dev`
- Azure OpenAI: `aoai-rag-demo-dev`
- Azure AI Search: `srch-rag-demo-dev`
- Search Index: `knowledge-index`

