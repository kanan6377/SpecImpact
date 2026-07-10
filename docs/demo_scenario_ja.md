# SpecImpact Agent Host デモシナリオ

## 目的

5分程度で「Dirty Excel投入から自然言語の変更影響レビューまで」を見せるための手順です。
外部公開時は`examples/dirty_sier_excel`だけを使い、実案件の設計書を録画に含めません。

## 事前準備

```powershell
python -m pip install -e ".[mcp,gui]"
specimpact init
specimpact agent doctor --host cursor --project .
specimpact gui --project .
```

Cursor Pluginをinstallし、Admin Consoleを`http://127.0.0.1:8765`で開いておきます。

## 収録

1. Cursorで`/specimpact-onboard`を実行する。
2. `examples/dirty_sier_excel/docs`を選択する。
3. Job ID、Workbook/Region件数、original保存を短く見せる。
4. 外部送信previewでhost、purpose、item count、redaction、source hashを確認して承認する。
5. Graph ProposalのEvidence IDとExcelセル範囲を見せ、1件をacceptする。
6. チャットへ次を入力する。

```text
入会申込画面の「利用限度額」の上限を999万円から9999万円に変更したい。
画面、validation、API、DB、外部IF、境界値テストへの影響と必要作業を調べて。
```

7. Change Atomのtarget/property/before/afterを見せる。
8. Impact Review projectionで候補、required action、Evidence、relation pathを見せる。
9. Evidenceを選び、Admin Consoleの設計書viewerで該当セルのハイライトへ移動する。
10. 1件をacceptedにし、同じstatusがCLIとObsidian exportへ反映されることを見せる。

## 説明する境界

- LLM出力はproposal/hypothesisで、最終判断ではない。
- Evidenceとgraph pathがなければ`must_review`にならない。
- Canvas/Artifact/Admin/Obsidianはprojectionで、JSONLがsource-of-truth。
- 設計書原本は自動編集しない。
- Host LLMだけで動き、SpecImpact provider API keyは不要。
