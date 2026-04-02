# 検索インデックスメンテナンス手順

## 概要
Azure AI Search のインデックスの構築・更新・再構築の手順を定義します。
RAG（検索拡張生成）システムの検索精度を維持するために定期的なメンテナンスが必要です。

## インデックス構成

### インデックス名
`knowledge-index`

### フィールド定義

| フィールド名 | 型 | 検索可能 | フィルタ可能 | ソート可能 | 説明 |
|-----------|-----|--------|-----------|----------|------|
| chunk_id | Edm.String | No | No | No | ドキュメントキー（必須・一意） |
| title | Edm.String | Yes | Yes | Yes | ドキュメントタイトル |
| section | Edm.String | Yes | Yes | No | セクション名 |
| source | Edm.String | No | Yes | No | ファイルパス |
| content | Edm.String | Yes | No | No | チャンク本文 |
| content_vector | Collection(Edm.Single) | No | No | No | Embeddingベクトル（1536次元） |

## インデックス構築コマンド

### 通常構築（差分更新）
```bash
cd backend
python scripts/build_index.py --mode update
```
- 既存のchunkを保持しつつ新規・更新ドキュメントのみ処理
- 処理時間の目安: ドキュメント100件あたり約5分

### 全件再構築
```bash
python scripts/build_index.py --mode rebuild
```
- インデックスを削除して再作成
- 全ドキュメントを再チャンク・再Embedding・再インデックス
- 処理時間の目安: ドキュメント100件あたり約15分
- **注意**: 再構築中は検索精度が低下する可能性あり（Embeddingの再計算中）

## 更新が必要なタイミング

1. **ドキュメントの追加・更新・削除**
   - docs/knowledge/ にファイルが追加・変更された場合
   - 手順: 差分更新モードで実行

2. **Embeddingモデルの変更**
   - モデルを text-embedding-ada-002 → text-embedding-3-large に変更した場合など
   - 手順: 全件再構築が必要（次元数が変わるため）

3. **チャンク設定の変更**
   - chunk_size や overlap 値を変更した場合
   - 手順: 全件再構築が必要

4. **定期メンテナンス**
   - 月1回、深夜バッチで差分更新を実行

## チャンク設定

| パラメータ | 設定値 | 理由 |
|-----------|-------|------|
| chunk_size | 500 tokens | コンテキスト精度とコスト のバランス |
| overlap | 100 tokens | セクション境界での文脈欠落を防ぐ |
| 分割単位 | Markdownの見出し（##）優先 | 意味的なまとまりを保持 |

## Embedding設定

| パラメータ | 設定値 |
|-----------|-------|
| モデル | text-embedding-3-large |
| 次元数 | 1536 |
| バッチサイズ | 16 |
| レート制限時待機 | Exponential Backoff（最大60秒） |

## モニタリング

構築後に確認すべき指標:
- インデックス内のドキュメント数（Azure Portal で確認）
- ストレージ使用量
- テストクエリへの応答精度（/api/search/debug エンドポイントで確認）

## よくある問題

### Embeddingが遅い / タイムアウトする
- Azure OpenAI のレート制限を確認
- バッチサイズを16から8に減らして再実行

### インデックス更新後に検索精度が低下した
- チャンク設定の変更がないか確認
- 全件再構築で解消することが多い
- /api/search/debug?q=テストクエリ でスコアを確認

### ベクトル検索が機能しない
- インデックスのベクトルフィールドの次元数とEmbeddingの次元数が一致しているか確認
- インデックスを削除して再構築

## 関連ドキュメント
- api-integration-guide.md
- batch-schedule-overview.md
