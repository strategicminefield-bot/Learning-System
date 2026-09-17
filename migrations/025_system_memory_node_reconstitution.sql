-- Section 25: System Memory & Node Reconstitution
-- 
-- Purpose: Persistent operational/procedural/node memory for AI node bootstrap
-- and reconstitution after context loss.
--
-- Extends Sections 6-14 knowledge infrastructure.
-- Does NOT duplicate; uses existing knowledge graph where applicable.
--
-- Memory Types:
-- - NODE_IDENTITY: stable node metadata
-- - ROLE: node capabilities/purpose/authority
-- - OPERATIONAL: environment/endpoints/references
-- - PROCEDURAL: how to perform recurring operations
-- - WORK: current assignment/state
-- - ORGANISATIONAL: relevant knowledge/learning (linked to existing)
--
-- Key principle: Memory is stored in Fabric. Node requests reconstitution
-- after context loss. Fabric assembles minimal bounded context.
-- Node does NOT need conversational history to be useful.

BEGIN;

-- ============================================================
-- SYSTEM MEMORY: Core persistent memory for nodes
-- ============================================================

CREATE TABLE IF NOT EXISTS system_memory (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Classification
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'node_identity',
        'node_role',
        'node_configuration',
        'operational_reference',
        'operational_procedure',
        'constraint',
        'linked_organisational',
        'work_state'
    )),
    
    -- Scope
    scope TEXT NOT NULL CHECK (scope IN ('node', 'role', 'system', 'task', 'provider')),
    scope_id UUID,  -- which node/role/task this applies to
    
    -- Content (flexible for different memory types)
    content JSONB NOT NULL,
    
    -- Versioning
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_memory_id UUID REFERENCES system_memory(memory_id),
    superseded_at TIMESTAMP WITH TIME ZONE,
    is_current BOOLEAN NOT NULL DEFAULT true,
    
    -- Provenance
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    created_by UUID,  -- node or operator
    updated_at TIMESTAMP WITH TIME ZONE,
    updated_by UUID,
    reason_for_change TEXT,
    
    -- Authority/Confidence
    authority_classification TEXT NOT NULL DEFAULT 'operational' 
        CHECK (authority_classification IN ('bootstrap', 'operational', 'procedural', 'advisory')),
    confidence NUMERIC NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    
    -- Lifecycle
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    effective_until TIMESTAMP WITH TIME ZONE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    
    -- Linked to historical/evidence sources
    linked_knowledge_id UUID REFERENCES knowledge(knowledge_id),
    linked_learning_id UUID,  -- reference to learning record if from evidence
    linked_attempt_id UUID REFERENCES attempts(attempt_id),
    linked_task_id UUID,
    
    -- Do NOT store secrets here
    is_secret_reference BOOLEAN NOT NULL DEFAULT false,
    secret_store_reference TEXT,  -- e.g. ".env.FABRIC_TOKEN"
    
    created_at_idx TIMESTAMP WITH TIME ZONE,
    is_current_idx BOOLEAN
);

CREATE INDEX ON system_memory(memory_type);
CREATE INDEX ON system_memory(scope, scope_id);
CREATE INDEX ON system_memory(is_current, memory_type);
CREATE INDEX ON system_memory(created_at DESC);
CREATE INDEX ON system_memory(effective_from, effective_until);
CREATE INDEX ON system_memory(scope_id) WHERE scope_id IS NOT NULL;

-- ============================================================
-- NODE PERSISTENT IDENTITY & BOOTSTRAP
-- ============================================================

CREATE TABLE IF NOT EXISTS node_bootstrap_config (
    bootstrap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    node_id UUID NOT NULL UNIQUE REFERENCES nodes(node_id),
    
    -- Minimum bootstrap needed to reconnect
    fabric_url TEXT NOT NULL,  -- e.g., http://95.179.236.41:8000
    adapter_type TEXT NOT NULL,  -- e.g., 'openclaw', 'openai'
    adapter_version TEXT,
    
    -- Stable identity persistence location
    -- e.g., ~/.openclaw/executor_config.json
    identity_store_path TEXT,
    identity_store_format TEXT DEFAULT 'json',
    
    -- Authentication reference (not credential itself)
    auth_mechanism TEXT NOT NULL CHECK (auth_mechanism IN (
        'gateway_managed',
        'local_config',
        'environment',
        'ssh_key',
        'oauth'
    )),
    auth_reference TEXT,  -- safe reference, not the secret
    
    -- Reconstitution entry point
    reconstitution_endpoint TEXT DEFAULT '/api/v1/nodes/{node_id}/reconstitute',
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    last_verified_at TIMESTAMP WITH TIME ZONE,
    
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX ON node_bootstrap_config(node_id);
CREATE INDEX ON node_bootstrap_config(adapter_type);

-- ============================================================
-- NODE RECONSTITUTION PACKAGE
-- ============================================================

CREATE TABLE IF NOT EXISTS node_reconstitution_packages (
    package_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    
    -- What triggered this reconstitution request
    request_reason TEXT NOT NULL CHECK (request_reason IN (
        'startup',
        'context_loss',
        'restart',
        'model_change',
        'manual_request',
        'periodic_sync',
        'recovery'
    )),
    
    -- Contents assembled
    package_content JSONB NOT NULL,  -- Full reconstitution context
    package_size_bytes INTEGER,
    context_window_utilization NUMERIC,  -- How much of AI context used
    
    -- Bounded retrieval info
    memory_categories_included TEXT[],  -- Which memory types included
    knowledge_items_included INTEGER,
    procedures_included INTEGER,
    
    -- Current work state (if any)
    current_assignment_id UUID REFERENCES assignments(assignment_id),
    current_task_id UUID,
    current_attempt_id UUID,
    
    -- Timestamps
    assembled_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    requested_by UUID,
    
    -- Verification
    verification_hash TEXT,  -- for integrity checking
    verified_by_node BOOLEAN,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX ON node_reconstitution_packages(node_id, created_at DESC);
CREATE INDEX ON node_reconstitution_packages(current_assignment_id);
CREATE INDEX ON node_reconstitution_packages(assembled_at DESC);

-- ============================================================
-- PROCEDURAL MEMORY: Operating procedures
-- ============================================================

CREATE TABLE IF NOT EXISTS procedural_memory (
    procedure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Procedure classification
    procedure_type TEXT NOT NULL CHECK (procedure_type IN (
        'startup',
        'assignment_claim',
        'task_execution',
        'result_submission',
        'error_handling',
        'reconnection',
        'context_recovery',
        'heartbeat',
        'status_report'
    )),
    
    provider_type TEXT NOT NULL,  -- 'openclaw', 'openai', etc.
    
    -- Procedure definition
    title TEXT NOT NULL,
    description TEXT,
    procedure_steps JSONB NOT NULL,  -- Array of steps with conditions
    
    -- Versioning
    version TEXT NOT NULL,  -- e.g., "1.0.0"
    version_notes TEXT,
    previous_procedure_id UUID,
    
    -- Applicability
    applicable_roles TEXT[],  -- Which node roles use this
    applicable_to_node_ids UUID[],  -- Specific nodes if needed
    conditions JSONB,  -- When to use this procedure
    
    -- Authority
    approved_by UUID,
    approved_at TIMESTAMP WITH TIME ZONE,
    supersedes_procedure_id UUID,
    
    -- Lifecycle
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    effective_until TIMESTAMP WITH TIME ZONE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    
    -- For audit/history
    change_reason TEXT,
    previous_version_reason TEXT
);

CREATE INDEX ON procedural_memory(procedure_type);
CREATE INDEX ON procedural_memory(provider_type);
CREATE INDEX ON procedural_memory(effective_from, effective_until);
CREATE INDEX ON procedural_memory(enabled) WHERE enabled = true;

-- ============================================================
-- WORK STATE RECOVERY
-- ============================================================

CREATE TABLE IF NOT EXISTS work_state_checkpoints (
    checkpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    
    -- What work is in progress
    task_id UUID,
    assignment_id UUID REFERENCES assignments(assignment_id),
    attempt_id UUID REFERENCES attempts(attempt_id),
    
    -- Checkpoint data
    checkpoint_data JSONB NOT NULL,  -- Current work state snapshot
    checkpoint_stage TEXT,  -- "started", "executing", "awaiting_response", etc.
    last_progress_timestamp TIMESTAMP WITH TIME ZONE,
    
    -- Recovery info
    is_recoverable BOOLEAN NOT NULL DEFAULT true,
    recovery_strategy TEXT,  -- 'continue', 'restart', 'retry'
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (now() + INTERVAL '7 days')
);

CREATE INDEX ON work_state_checkpoints(node_id, created_at DESC);
CREATE INDEX ON work_state_checkpoints(assignment_id);
CREATE INDEX ON work_state_checkpoints(attempt_id);
CREATE INDEX ON work_state_checkpoints(expires_at);

-- ============================================================
-- MEMORY ACCESS LOG (for observability)
-- ============================================================

CREATE TABLE IF NOT EXISTS memory_access_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    
    -- What was accessed
    access_type TEXT NOT NULL CHECK (access_type IN (
        'bootstrap_retrieval',
        'reconstitution_package',
        'procedure_lookup',
        'work_state_recovery',
        'knowledge_retrieval',
        'memory_write'
    )),
    
    memory_category TEXT,
    memory_ids_accessed UUID[],
    
    -- Context
    reason TEXT,
    context JSONB,
    
    -- Result
    success BOOLEAN,
    result_summary TEXT,
    items_returned INTEGER,
    context_bytes_returned INTEGER,
    
    -- Timing
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms NUMERIC,
    
    -- Verification
    verified_at_node BOOLEAN
);

CREATE INDEX ON memory_access_log(node_id, requested_at DESC);
CREATE INDEX ON memory_access_log(access_type);
CREATE INDEX ON memory_access_log(requested_at DESC);

-- ============================================================
-- LINK: System Memory to existing Knowledge/Learning
-- ============================================================

CREATE TABLE IF NOT EXISTS system_memory_to_knowledge (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    system_memory_id UUID NOT NULL REFERENCES system_memory(memory_id),
    knowledge_id UUID NOT NULL REFERENCES knowledge(knowledge_id),
    
    -- Relationship type
    relationship_type TEXT CHECK (relationship_type IN (
        'sourced_from',
        'derived_from',
        'supports',
        'validates',
        'supersedes'
    )),
    
    -- Context
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX ON system_memory_to_knowledge(system_memory_id);
CREATE INDEX ON system_memory_to_knowledge(knowledge_id);

-- ============================================================
-- COMMIT
-- ============================================================

COMMIT;
