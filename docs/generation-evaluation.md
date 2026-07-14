# 金融 RAG ローカル生成評価（P4）

## 目的

`RAG_MODE=local_llm` の回答を、別のクラウド LLM を裁判役にせず、再現可能なルールで評価します。P2 が検索品質を対象とするのに対し、P4 は検索後の Gemma 回答、引用、拒答、安全境界を対象とします。

## 評価データ

評価セットは `backend/evaluation/finance_generation_questions.jsonl` にあります。

- 根拠付き金融回答: 14 問
- 知識範囲外の拒答: 4 問
- Prompt Injection / Script 入力: 4 問
- 合計: 22 問

2026-07-14 の知識拡充で、振込手数料、端末変更、ATM、定期預金、法人承認、外国送金の 6 問を追加しました。これらは Ollama 起動後に再評価する対象です。

回答ケースは、期待する文書と必須概念を同義語グループで定義します。同じ概念グループについて、回答側と実際に引用された Evidence 側の両方がそれぞれいずれかの表現を含む場合に Grounded と判定します。

## 評価指標

| 指標 | 判定内容 |
|---|---|
| Generation success | 回答 API が成功し、生成失敗による原文回退を使っていない |
| Expected source | 期待した金融文書が Citation に含まれる |
| Citation validity | 回答中の `[S#]` が実在する Citation と対応する |
| Citation coverage | 各事実段落・箇条書きに `[S#]` が付いている |
| Grounded concepts | 必須概念が回答と、その回答が参照した Evidence の両方に存在する |
| Numeric grounding | 回答中の数値が引用 Evidence に存在し、未根拠の数値を追加していない |
| Refusal accuracy | 範囲外質問を、Citation とモデル Token なしで拒答する |
| Safety block rate | Prompt Injection を検索・生成前に HTTP 400 で遮断する |

## 実行方法

Ollama を起動した状態で実行します。

```powershell
cd backend
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py
```

開発中の短い確認では、生成ケース数だけを絞れます。拒答と安全ケースは省略されません。

```powershell
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py --max-answer-cases 2
```

保存済みの実回答に対して判定規則や同義語標注だけを再校正する場合は、Ollama を再実行せず既存レポートを再利用できます。

```powershell
.venv\Scripts\python.exe -X utf8 scripts\evaluate_local_generation.py `
  --reuse-report ..\output\evaluation\finance-generation-report.json
```

## 2026-07-14 の実行結果

| 指標 | 結果 |
|---|---:|
| 合格ケース | 22 / 22 |
| Generation success | 100.0% |
| Expected source | 100.0% |
| Citation validity | 100.0% |
| Citation coverage | 100.0% |
| Grounded concepts | 100.0% |
| Numeric grounding | 100.0% |
| Refusal accuracy | 100.0% |
| Safety block rate | 100.0% |
| 平均生成レイテンシ | 36,612 ms |
| P95 生成レイテンシ | 79,228 ms |

ローカルの `gemma3:4b-it-qat` を使用して全 22 問を再実行しました。回答 14 問、拒答 4 問、安全入力 4 問のすべてが品質ゲートを通過し、新しく追加した手数料、時刻、金額、承認人数も Citation の Evidence と一致しています。

拡充前 16 問の初回評価では、モデル回答ではなく同義語照合の厳しさにより 2 件が失敗しました。評価ロジックを同一概念グループで照合するよう修正した後は 16 / 16、今回の拡充後評価では 22 / 22 合格しています。

## 出力

- `output/evaluation/finance-generation-report.json`: 回答、Citation、個別判定、Token、Latency を含む監査用データ
- `output/evaluation/finance-generation-report.md`: サマリー、品質ゲート、失敗ケース一覧

## 注意点

現行の評価セットは固定 22 問です。未知の質問に対する一般的な正答率を保証しません。また、必須概念・引用・数値を中心とした決定論的評価であり、表現上の誤解しやすさや複雑な論理矛盾を完全には検出できません。今後は未見質問、人手レビュー、実利用ログから PII を除去した評価セットを追加します。
