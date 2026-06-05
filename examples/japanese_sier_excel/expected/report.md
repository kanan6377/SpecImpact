# Expected Impact Report

## Change Request

入会申込画面の「利用限度額」の上限を999万円から9999万円に変更する。

## Summary

- must_review review artifacts: 6
- should_review: 1
- may_review: 0

This sample may also include a direct BusinessField match for `requestedCreditLimit`.
The review table value is in the traceable artifacts below.

## must_review

### 入会申込画面

- type: Screen
- reason: 利用限度額を表示・入力しているため
- evidence:
  - 画面設計書.xlsx / 画面項目定義 / row 3 / cell D3

### 入会申込API

- type: API
- reason: requestedCreditLimit を request field として受け取るため
- evidence:
  - API定義書.xlsx / 入会申込API / row 3 / cell F3

### REQUESTED_CREDIT_LIMIT

- type: Column
- reason: 利用限度額がDBカラムに保存されるため
- evidence:
  - テーブル定義書.xlsx / CREDIT_APPLICATION / row 4 / cell C4

### 利用限度額入力チェック

- type: ValidationRule
- reason: requestedCreditLimit に対する上限値チェックがあるため
- evidence:
  - 入力チェック一覧.xlsx / 入力チェック一覧 / row 3 / cell D3

### 外部与信IF

- type: ExternalIF
- reason: requestedCreditLimit を外部与信IFへ送信するため
- evidence:
  - 外部IF定義書.xlsx / 外部与信IF / row 3 / cell F3

### 境界値テスト

- type: TestCase
- reason: requestedCreditLimit の上限境界値を試験しているため
- evidence:
  - 試験項目書.xlsx / 入会申込境界値テスト / row 2 / cell D2

## should_review

### 申込確認画面

- type: Screen
- reason: 利用限度額を表示しているため、確認画面の表示・文言を確認する
- evidence:
  - 画面設計書.xlsx / 画面項目定義 / row 4 / cell D4

## Notes

このレポートは影響確定結果ではなく、レビュー候補です。
must_review は「影響あり」ではなく「必ず確認すべき」です。
