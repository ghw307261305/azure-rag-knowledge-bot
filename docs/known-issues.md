# Known Issues & 制限事項

本ドキュメントは現在の実装における既知の制限事項を記録します。
POC フェーズとして意図的に対応を後回しにしているものも含みます。

---

## 機能面の制限

### 1. 原始会話履歴はサーバー側で保持しない
- 会話履歴はブラウザの `localStorage` に保存されるため、同じブラウザでは再読込後も表示できる
- サーバー側が保存するのは PII 清洗後の明示的な preference / fact のみで、原始質問・回答全文ではない
- 過去の発言全文を使うマルチターン質問（「それについてもう少し詳しく」など）には未対応
- **対応方針**: 認証ユーザー単位の暗号化セッションストレージと、保存範囲を制限した会話要約を追加する

### 2. 本番向け認証・認可が未実装
- ローカル短期 JWT、user / operator / admin、文書 ACL Filter は実装済み
- 現在の JWT は Entra ID の代替ではなく、署名鍵配布、失効、MFA、実ユーザーグループ連携は未実装
- **対応方針**: Microsoft Entra ID + MSAL/JWT 検証へ差し替え、ACL を Entra Group に接続する

### 3. Query Rewrite が latency を増加させる
- 毎回 GPT-4o を呼び出してクエリを書き換えるため、+1〜2 秒の遅延がある
- **対応方針**: 短い質問やキーワードのみの質問はスキップするロジックを追加

### 4. Azure 検索スコアの閾値が調整されていない
- ローカル検索は `LOCAL_MIN_SCORE` で調整できるが、Azure 経路は暫定値を使用している
- 実際の Azure 検索結果と未見質問を使い、回答率と誤回答率のバランスを調整する必要がある

### 5. ドキュメントの更新がリアルタイムに反映されない
- `docs/knowledge/` を更新しても、手動で `build_index.py` を実行しないと検索に反映されない
- **対応方針**: ファイル変更を検知して自動再インデックスする仕組みを追加（例: GitHub Actions trigger）

---

## セキュリティ面の制限

### 6. Prompt Injection 防護が基本的なパターンマッチのみ
- 現在は固定パターンリストによる簡易検出のみ
- 巧妙な Prompt Injection 攻撃には対応していない
- **対応方針**: Azure AI Content Safety の統合

### 7. API レート制限が未実装
- 悪意あるユーザーが大量リクエストを送った場合の防護がない
- **対応方針**: FastAPI の slowapi ライブラリ等でレート制限を追加

---

## 運用面の制限

### 8. ログと Trace の本番保存先が未確定
- Request ID、JSON 構造化ログ、Prometheus endpoint、任意の OTLP Trace 出力は実装済み
- 本番の保存期間、Dashboard、Alert、PII 監査、Application Insights 接続は未検証
- **対応方針**: 実環境の監視基盤と SLO に合わせて保存・通知・権限を設定する

### 9. インデックス再構築中はサービス品質が低下する可能性がある
- `build_index.py --rebuild` 実行中は古いインデックスと新しいインデックスが混在する
- **対応方針**: Blue-Green 方式のインデックス切り替えを実装

### 10. CI はあるが Azure 自動デプロイは未有効化
- GitHub Actions で Backend、Frontend、Bicep、品質評価、Secret Scan を実行する
- Azure 環境が利用できないため、Staging Slot、Smoke Test、承認、Rollback を含む配備は未検証
- **対応方針**: Azure 復旧後に環境別承認付き Deployment Job を追加する
