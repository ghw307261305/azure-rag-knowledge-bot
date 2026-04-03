# オンボーディング・引き継ぎチェックリスト

## 概要
新メンバーがプロジェクトに参加する際、または担当変更の際に確認すべき事項をまとめます。

## 環境セットアップ

### 必要なアクセス権限
- [ ] Azure サブスクリプションへのアクセス（Contributor 以上）
- [ ] GitHub リポジトリへのアクセス（Write 権限）
- [ ] Azure DevOps / プロジェクト管理ツールへのアクセス
- [ ] 本番ログ閲覧権限（Azure Monitor / Application Insights）
- [ ] Slackの関連チャンネル参加（#dev, #障害対応, #リリース）

### ローカル環境構築
1. リポジトリのクローン
2. .env ファイルの作成（.env.example を参照）
3. Python 仮想環境の作成とパッケージインストール
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
4. Node.js パッケージインストール
   ```bash
   cd frontend
   npm install
   ```
5. バックエンド起動確認: `uvicorn main:app --reload`
6. フロントエンド起動確認: `npm run dev`
7. `/api/health` が 200 を返すことを確認

## ドキュメント確認

- [ ] README.md を通読
- [ ] docs/architecture.md（システム全体像）
- [ ] docs/api-spec.md（API仕様）
- [ ] docs/known-issues.md（既知の問題）
- [ ] docs/review-checklist.md（レビュー観点）
- [ ] docs/knowledge/（業務ナレッジ）の主要ドキュメント

## システム理解チェックポイント

以下の質問に答えられるようになることが目標:

1. RAGの基本的なフローを説明できる（検索→コンテキスト組み立て→生成）
2. Azure AI Searchのhybrid searchがなぜ有効かを説明できる
3. chunk_sizeとoverlapの意味と設定値の根拠を説明できる
4. インデックスの再構築が必要なタイミングを3つ挙げられる
5. 本番環境で障害が発生した場合の初動対応を説明できる
6. 環境（local/dev/staging/prod）ごとの認証方式の違いを説明できる

## 引き継ぎ事項（担当変更時）

前任者が準備すること:
- [ ] 未完了タスクの一覧と現状
- [ ] 進行中のバグ・課題のステータス
- [ ] 注意が必要な既知の制限・回避策
- [ ] 外部ベンダー・クライアントとのやり取り状況
- [ ] リリース予定とデプロイ手順の確認

後任者が確認すること:
- [ ] 上記ドキュメント確認
- [ ] ローカル環境の動作確認
- [ ] staging/prod 環境へのアクセス確認
- [ ] 前任者との1時間のQ&Aセッション実施

## よくある新規参加者の疑問

### Q. どこから読み始めればいいですか？
A. docs/architecture.md → README.md → docs/knowledge/ の順に読むのが効率的です。

### Q. ローカルで動作確認するのに Azure 接続は必要ですか？
A. 初期の動作確認は mock モードで可能です。`.env` に実際の Azure キーがなくても `/api/chat` は mock データを返します。

### Q. 本番環境のログはどこで見られますか？
A. Azure Portal > Application Insights > ログ（Kusto クエリ）で確認できます。アクセス権限の付与を先に依頼してください。

### Q. コードレビューの基準はありますか？
A. docs/review-checklist.md を参照してください。

## 関連ドキュメント
- incident-response-procedure.md
- release-deployment-process.md
