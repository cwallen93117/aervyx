-- Phase 2: add result_state column to score_results.
-- Values: 'provisional' or 'official'. Existing rows default to 'official'.

ALTER TABLE score_results
    ADD COLUMN result_state VARCHAR(20) NOT NULL DEFAULT 'official';

CREATE INDEX ix_score_results_result_state ON score_results (result_state);
