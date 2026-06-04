# Database Schema

## Table: CARD_APPLICATION
- application_id
- applicant_id
- requested_credit_limit
- screening_status
- created_at

## Table: APPLICANT_PROFILE
- applicant_id
- applicant_name
- birth_date
- address
- phone_number
- email
- employer_name
- annual_income

## Table: SCREENING_RESULT
- screening_id
- application_id
- credit_score
- fraud_risk_score
- decision
