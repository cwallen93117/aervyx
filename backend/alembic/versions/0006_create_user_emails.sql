-- Create user_emails table for additional email addresses per user.
-- Used for pilot record matching during registration and self-service claim.

CREATE TABLE user_emails (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email           VARCHAR(160) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_user_emails_email ON user_emails (email);
CREATE INDEX ix_user_emails_user_id ON user_emails (user_id);
