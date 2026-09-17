BEGIN;

-- Worker status history for tracking node availability and metrics
CREATE TABLE IF NOT EXISTS worker_status_history (
    status_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    previous_status TEXT,
    current_status TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Worker metrics for tracking performance and load
CREATE TABLE IF NOT EXISTS worker_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    average_quality_score NUMERIC,
    successful_attempts INTEGER DEFAULT 0,
    total_attempts INTEGER DEFAULT 0,
    last_heartbeat TIMESTAMPTZ,
    uptime_seconds INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Worker capabilities tracking
CREATE TABLE IF NOT EXISTS worker_capabilities (
    capability_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    capability_name TEXT NOT NULL,
    capability_version TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    performance_rating NUMERIC DEFAULT 1.0,
    last_used TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(node_id, capability_name)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_status_history_node ON worker_status_history(node_id);
CREATE INDEX IF NOT EXISTS idx_status_history_created ON worker_status_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_node ON worker_metrics(node_id);
CREATE INDEX IF NOT EXISTS idx_metrics_heartbeat ON worker_metrics(last_heartbeat DESC);
CREATE INDEX IF NOT EXISTS idx_capabilities_node ON worker_capabilities(node_id);
CREATE INDEX IF NOT EXISTS idx_capabilities_enabled ON worker_capabilities(enabled);

COMMIT;
