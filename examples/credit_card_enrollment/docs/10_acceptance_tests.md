# Acceptance Tests

## TestCase: 正常な入会申込
Covers: カード入会申込API, カード入会申込画面

## TestCase: 希望利用限度額の上限超過
Covers: 希望利用限度額チェック, カード入会申込API
Asserts: requestedCreditLimit が100万円を超える場合はエラー

## TestCase: 年収に対して希望利用限度額が高い場合
Covers: 希望利用限度額チェック, 信用審査API
Asserts: 年収の50%を超える場合は manual_review
