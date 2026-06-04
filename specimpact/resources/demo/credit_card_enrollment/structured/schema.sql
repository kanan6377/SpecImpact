CREATE TABLE CARD_APPLICATION (
  application_id VARCHAR(40) PRIMARY KEY,
  applicant_id VARCHAR(40) NOT NULL,
  requested_credit_limit INTEGER NOT NULL,
  screening_status VARCHAR(30),
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE SCREENING_RESULT (
  screening_id VARCHAR(40) PRIMARY KEY,
  application_id VARCHAR(40) NOT NULL,
  decision VARCHAR(30),
  CONSTRAINT fk_application FOREIGN KEY (application_id) REFERENCES CARD_APPLICATION(application_id)
);
