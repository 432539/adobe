-- Dual Adobe identity lanes. Apply once in production before deploying the new worker.
-- Existing group/status/plan_cap values are intentionally preserved.
ALTER TABLE upstream_accounts ADD COLUMN IF NOT EXISTS ios_device_token_enc TEXT;
ALTER TABLE upstream_accounts ADD COLUMN IF NOT EXISTS ios_device_id_enc TEXT;
ALTER TABLE upstream_accounts
    ADD COLUMN IF NOT EXISTS credential_status VARCHAR(16) NOT NULL DEFAULT 'unverified';
ALTER TABLE upstream_accounts ADD COLUMN IF NOT EXISTS credential_error VARCHAR(255);
ALTER TABLE upstream_accounts ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;

