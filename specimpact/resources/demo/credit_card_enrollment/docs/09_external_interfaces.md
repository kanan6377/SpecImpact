# External Interfaces

## ExternalIF: 本人確認サービス
Sends: applicantName, birthDate, address

## ExternalIF: 信用情報照会サービス
Sends: applicantName, birthDate, address
Receives: creditScore

## ExternalIF: 不正検知サービス
Sends: phoneNumber, email, address, requestedCreditLimit
Receives: fraudRiskScore

## ExternalIF: メール通知サービス
Sends: email, screeningStatus
