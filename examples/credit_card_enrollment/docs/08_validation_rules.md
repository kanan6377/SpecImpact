# Validation Rules

## ValidationRule: 希望利用限度額チェック
Target: requestedCreditLimit / CARD_APPLICATION.requested_credit_limit

Rule:
- 希望利用限度額は10万円以上100万円以下
- 年収の50%を超える場合は manual_review

## ValidationRule: 年収チェック
Target: annualIncome

Rule:
- 0円以上
- 申告年収が未入力の場合はエラー
