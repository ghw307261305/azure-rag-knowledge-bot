# 金融ナレッジ ローカル検索評価

## 目的

ローカル検索が期待する金融文書を上位に返し、知識範囲外の質問を Fallback できることを、生成モデル接続前に定量化します。これにより、後続の Ollama / Azure OpenAI 評価で「検索の問題」と「回答生成の問題」を分離できます。

## 評価データ

評価セットは `backend/evaluation/finance_questions.jsonl` にあります。

- 全 88 問
- 回答可能 76 問
- 回答不能 12 問
- 26 文書、142 Chunk の架空金融ナレッジをカバー
- KYC、口座、振込、手数料、限度額、ネットバンキング、ATM、顧客情報変更、定期預金、法人振込、外国送金、AML、融資、リスク、苦情、サイバー、BCP、規制変更を含む
- 市況、税務、保険、年金、旧採用業務などの範囲外質問を含む

各レコードには質問、カテゴリ、回答可能性、期待するソース、期待する証拠キーワードがあります。

## 実行方法

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_retrieval.py
```

出力：

- `output/evaluation/finance-retrieval-report.json`
- `output/evaluation/finance-retrieval-report.md`

品質ゲートを満たさない場合、コマンドは終了コード 1 を返します。

## 指標

| 指標 | 意味 | P2 ゲート |
|---|---|---:|
| Hit@3 | 期待ソースが上位 3 件に存在する割合 | 90% 以上 |
| MRR@5 | 期待ソース順位の逆数平均 | 参考値 |
| Fallback Accuracy | 範囲外質問を回答不能と判定できた割合 | 95% 以上 |
| Answerability Accuracy | 回答可能 / 不可能の判定正解率 | 95% 以上 |
| Keyword Coverage | Top-5 証拠に期待キーワードが含まれる割合 | 90% 以上 |
| P95 Latency | 検索時間の 95 パーセンタイル | 参考値 |

## 拡充後ベースライン

2026-07-14 のローカル評価結果：

| 指標 | 結果 |
|---|---:|
| ケース合格 | 88 / 88 |
| Hit@1 | 90.8% |
| Hit@3 / Hit@5 | 100.0% / 100.0% |
| MRR@5 | 0.9518 |
| Fallback Accuracy | 100.0% |
| Answerability Accuracy | 100.0% |
| Keyword Coverage | 100.0% |
| 平均 / P95 検索時間 | 2.446 / 3.455 ms |

分塊処理から重複 H1 Chunk を除外し、タイトル・章名へ適度な重みを付けました。評価で確認した正解・不正解スコアの分布に基づき、ローカル Fallback 閾値を `0.06` に設定しています。

## 解釈上の注意

この 100% は、リポジトリ内で作成した固定評価セットに対する検索結果です。実利用者の質問、誤字、曖昧表現、新しい商品・規制を含む一般的な正答率を意味しません。特に、今回追加した手数料・限度額・受付時間は架空の基準値です。次段階では、別担当者が作成した未見質問と実利用ログを追加し、データ漏洩を避けた回帰評価を行います。

また、この評価は検索品質のみを対象とします。自然言語回答の Groundedness、Citation 一致、拒答、安全性は、P4 の [`generation-evaluation.md`](generation-evaluation.md) で別途評価します。
