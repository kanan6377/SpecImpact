# カード入会申込API

## Endpoint
POST /api/card-applications

## Request fields
- applicantName
- birthDate
- address
- phoneNumber
- email
- employerName
- annualIncome
- requestedCreditLimit: 希望利用限度額。10万円〜100万円。
- bankAccountNumber

## Response fields
- applicationId
- screeningStatus
- message

## Writes
- CARD_APPLICATION
- APPLICANT_PROFILE

## Calls
- 信用審査API
- 本人確認外部IF
- 不正検知外部IF
