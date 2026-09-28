-- Section 26: Push-Range Advisory Review
-- Purpose: Advisory/shadow review of git push ranges with mechanical checks.
-- Based on PRAGMA: Push-Range Advisory Git Mechanical Assessment
-- Date: 2026-09-28

CREATE TABLE IF NOT EXISTS check_spec (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    check_type TEXT NOT NULL DEFAULT 'mechanical',
    severity TEXT NOT NULL DEFAULT 'advisory',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS push_review_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base_sha TEXT NOT NULL,
    head_sha TEXT NOT NULL,
    repo_path TEXT NOT NULL DEFAULT '/opt/learning-fabric',
    total_advisories INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS advisory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES push_review_run(id),
    check_spec_id UUID NOT NULL REFERENCES check_spec(id),
    reason TEXT NOT NULL,
    requested_action TEXT,
    severity TEXT NOT NULL DEFAULT 'advisory',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS advisory_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    advisory_id UUID NOT NULL REFERENCES advisory(id),
    evidence_table TEXT NOT NULL,
    evidence_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS advisory_observation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    advisory_id UUID NOT NULL REFERENCES advisory(id),
    observation_type TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incident (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    summary TEXT NOT NULL,
    impact TEXT,
    affected_path_globs TEXT[],
    evidence_refs JSONB,
    severity TEXT NOT NULL DEFAULT 'advisory',
    status TEXT NOT NULL DEFAULT 'open',
    check_spec_id UUID REFERENCES check_spec(id),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Register migration
INSERT INTO schema_migrations (version, applied_at)
VALUES ('026-push-review-advisory', now())
ON CONFLICT (version) DO NOTHING;
