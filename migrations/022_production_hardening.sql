-- Migration 022: Production Hardening
-- 
-- Adds operational tables and improvements for 24/7 production reliability.

-- Operation audit log: Track all significant operations for failure isolation and debugging
CREATE TABLE IF NOT EXISTS operation_audit_log (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id UUID NOT NULL,
    operation_type VARCHAR(100) NOT NULL,
    actor_type VARCHAR(50),
    actor_reference VARCHAR(255),
    status VARCHAR(50) NOT NULL,  -- running, succeeded, failed, timeout
    error_message TEXT,
    duration_ms BIGINT,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operation_audit_operation_id ON operation_audit_log(operation_id);
CREATE INDEX IF NOT EXISTS idx_operation_audit_status ON operation_audit_log(status);
CREATE INDEX IF NOT EXISTS idx_operation_audit_recorded_at ON operation_audit_log(recorded_at DESC);

-- Production configuration
CREATE TABLE IF NOT EXISTS production_config (
    config_id SERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL UNIQUE,
    config_value TEXT,
    config_type VARCHAR(50),  -- string, integer, boolean, json
    is_secret BOOLEAN DEFAULT false,
    required_at_startup BOOLEAN DEFAULT false,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default production configuration
INSERT INTO production_config (config_key, config_value, config_type, required_at_startup, description)
VALUES
    ('api_timeout_seconds', '30', 'integer', true, 'API request timeout'),
    ('db_connection_timeout_seconds', '10', 'integer', true, 'Database connection timeout'),
    ('db_pool_max_size', '10', 'integer', true, 'Maximum database connections'),
    ('max_retry_attempts', '3', 'integer', false, 'Maximum retry attempts for transient failures'),
    ('retry_backoff_ms', '100', 'integer', false, 'Initial retry backoff in milliseconds'),
    ('governance_timeout_ms', '5000', 'integer', true, 'Governance evaluation timeout'),
    ('max_request_size_kb', '1024', 'integer', false, 'Maximum request body size'),
    ('max_task_batch_size', '1000', 'integer', false, 'Maximum tasks in batch operations')
ON CONFLICT DO NOTHING;

-- Health check history (for trend detection)
CREATE TABLE IF NOT EXISTS health_check_history (
    check_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_type VARCHAR(100),  -- api, database, governance, evaluation
    status VARCHAR(50),  -- healthy, degraded, unhealthy
    details JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_check_type ON health_check_history(check_type);
CREATE INDEX IF NOT EXISTS idx_health_check_status ON health_check_history(status);
CREATE INDEX IF NOT EXISTS idx_health_check_checked_at ON health_check_history(checked_at DESC);

-- Deployment events (track deployments for troubleshooting)
CREATE TABLE IF NOT EXISTS deployment_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_type VARCHAR(100),  -- api, migration, rollback
    previous_version VARCHAR(100),
    new_version VARCHAR(100),
    status VARCHAR(50),  -- in_progress, completed, failed, rolled_back
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    deployed_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_deployment_events_status ON deployment_events(status);
CREATE INDEX IF NOT EXISTS idx_deployment_events_completed_at ON deployment_events(completed_at DESC);

-- Data integrity findings (from audit procedures)
CREATE TABLE IF NOT EXISTS integrity_findings (
    finding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_type VARCHAR(100),  -- orphaned_reference, invalid_state, missing_evidence, constraint_violation
    affected_entity_type VARCHAR(100),
    affected_entity_id VARCHAR(255),
    severity VARCHAR(50),  -- info, warning, critical
    description TEXT,
    repair_action TEXT,
    found_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    repaired_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_integrity_findings_severity ON integrity_findings(severity);
CREATE INDEX IF NOT EXISTS idx_integrity_findings_found_at ON integrity_findings(found_at DESC);

-- Application event log (structured logging)
CREATE TABLE IF NOT EXISTS application_event_log (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100),  -- startup, shutdown, error, warning, governance_denial, failure_recovery
    severity VARCHAR(50),  -- debug, info, warning, error, critical
    component VARCHAR(100),  -- api, orchestration, experimentation, validation, evolution, self_org, governance, evaluation
    correlation_id VARCHAR(255),  -- to link related events across operations
    message TEXT,
    context_data JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_event_type ON application_event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_app_event_severity ON application_event_log(severity);
CREATE INDEX IF NOT EXISTS idx_app_event_component ON application_event_log(component);
CREATE INDEX IF NOT EXISTS idx_app_event_correlation_id ON application_event_log(correlation_id);
CREATE INDEX IF NOT EXISTS idx_app_event_occurred_at ON application_event_log(occurred_at DESC);

-- Service status (for readiness probes)
CREATE TABLE IF NOT EXISTS service_status (
    status_id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) UNIQUE NOT NULL,
    health_status VARCHAR(50),  -- starting, healthy, degraded, unhealthy, stopping
    readiness_status VARCHAR(50),  -- ready, not_ready, recovering
    last_heartbeat TIMESTAMP WITH TIME ZONE,
    details JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO service_status (service_name, health_status, readiness_status)
VALUES
    ('api', 'starting', 'not_ready'),
    ('database', 'starting', 'not_ready'),
    ('governance', 'starting', 'not_ready'),
    ('evaluation', 'starting', 'not_ready')
ON CONFLICT DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_service_status_updated_at ON service_status(updated_at DESC);

-- Backup manifest (track backup metadata)
CREATE TABLE IF NOT EXISTS backup_manifest (
    backup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backup_type VARCHAR(50),  -- full, incremental
    backup_location TEXT,
    backup_size_bytes BIGINT,
    tables_backed_up INT,
    rows_sampled BIGINT,
    backup_started_at TIMESTAMP WITH TIME ZONE,
    backup_completed_at TIMESTAMP WITH TIME ZONE,
    restore_tested_at TIMESTAMP WITH TIME ZONE,
    restore_test_result VARCHAR(50),  -- passed, failed, not_tested
    retention_expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_backup_manifest_completed_at ON backup_manifest(backup_completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_backup_manifest_expires_at ON backup_manifest(retention_expires_at DESC);
