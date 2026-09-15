BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE requests
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'received';

ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS requests_status_check;

ALTER TABLE requests
    ADD CONSTRAINT requests_status_check
    CHECK (status IN ('received','queued','in_progress','completed','failed','cancelled'));

CREATE INDEX IF NOT EXISTS requests_status_idx ON requests(status);

CREATE TABLE IF NOT EXISTS node_capabilities (
    node_id uuid NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    capability text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, capability)
);

CREATE INDEX IF NOT EXISTS node_capabilities_capability_idx
    ON node_capabilities(capability);

INSERT INTO schema_migrations(version)
VALUES ('001-foundation-lifecycle-capabilities')
ON CONFLICT (version) DO NOTHING;

COMMIT;
