CREATE TABLE IF NOT EXISTS passkey_credentials (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  credential_id VARCHAR(1024) NOT NULL,
  public_key BYTEA NOT NULL,
  user_handle BYTEA NOT NULL,
  sign_count INTEGER NOT NULL DEFAULT 0,
  transports JSON,
  aaguid VARCHAR(36),
  name VARCHAR(80) NOT NULL DEFAULT 'Passkey',
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  last_used_at TIMESTAMPTZ,
  CONSTRAINT uq_passkey_credentials_credential_id UNIQUE (credential_id)
);

CREATE INDEX IF NOT EXISTS ix_passkey_credentials_user_id ON passkey_credentials(user_id);
CREATE INDEX IF NOT EXISTS ix_passkey_credentials_user_handle ON passkey_credentials(user_handle);

CREATE TABLE IF NOT EXISTS passkey_challenges (
  id VARCHAR(64) PRIMARY KEY,
  challenge BYTEA NOT NULL,
  purpose VARCHAR(20) NOT NULL,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_passkey_challenges_expires_at ON passkey_challenges(expires_at);
