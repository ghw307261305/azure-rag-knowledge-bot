# リリース・デプロイ手順

## 概要
本ドキュメントでは、本システムのリリース判断基準、デプロイ手順、およびロールバック方法を定義します。

## ブランチ戦略

```
main          ← 本番環境 (production)
  ↑ PR merge
staging       ← 検証環境 (staging)
  ↑ PR merge
develop       ← 開発環境 (development)
  ↑ feature branch merge
feature/xxx   ← 機能開発ブランチ
```

## リリース判断基準

本番リリース前に以下をすべて満たすこと:

- [ ] 自動テスト（unit + integration）がすべて Pass
- [ ] staging 環境での動作確認完了
- [ ] セキュリティチェック（依存パッケージの脆弱性スキャン）Pass
- [ ] PM / リーダーのレビュー承認
- [ ] リリースノートの作成
- [ ] リリース当日の担当者確認（ロールバック対応者）

## デプロイ手順（GitHub Actions 自動）

### 検証環境（staging）へのデプロイ
1. `develop` ブランチへの PR マージをトリガー
2. GitHub Actions が自動実行:
   - テスト実行
   - Dockerイメージビルド（または zip デプロイ）
   - staging 環境へ自動デプロイ
3. デプロイ完了後にSlack通知

### 本番環境（production）へのデプロイ
1. `staging` → `main` への PR 作成
2. レビュー・承認
3. マージをトリガーに GitHub Actions が自動実行:
   - 本番環境へデプロイ
   - スモークテスト実行（主要エンドポイントへのヘルスチェック）
4. デプロイ完了後にSlack通知
5. 本番確認（担当者が手動でブラウザ確認）

## 手動デプロイ（緊急対応時）

Azure CLI を使用:

```bash
# バックエンド（App Service）
az webapp deploy \
  --resource-group rg-rag-prod \
  --name app-rag-backend-prod \
  --src-path ./backend.zip \
  --type zip

# フロントエンド（Static Web Apps）
swa deploy ./frontend/dist \
  --deployment-token $SWA_TOKEN \
  --env production
```

## ロールバック手順

### App Service（バックエンド）
```bash
# デプロイスロットを利用している場合
az webapp deployment slot swap \
  --resource-group rg-rag-prod \
  --name app-rag-backend-prod \
  --slot staging \
  --target-slot production

# デプロイ履歴から戻す場合
az webapp deployment list --name app-rag-backend-prod \
  --resource-group rg-rag-prod
az webapp deployment rollback --name app-rag-backend-prod \
  --resource-group rg-rag-prod
```

### Static Web Apps（フロントエンド）
- GitHub Actions で前バージョンのコミットを指定して再デプロイ

## デプロイ後の確認チェックリスト

- [ ] `/api/health` が 200 を返す
- [ ] ログイン動作確認
- [ ] 主要な求人検索が動作する
- [ ] チャット機能が動作する（RAG検索確認）
- [ ] Application Insights でエラーレート上昇なし

## デプロイ禁止時間帯

- 月末・月初（1日・末日）: バッチ処理と重複リスク
- 平日 9:00〜12:00: ユーザー利用ピーク
- 重要イベント期間（採用シーズン等）

## 関連ドキュメント
- incident-response-procedure.md
- batch-schedule-overview.md
