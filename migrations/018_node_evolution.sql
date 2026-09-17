-- Section 18: Node Evolution Layer
-- Manages node definition versioning, capability evolution, specialisation
-- and evidence-based configuration proposals without autonomous provisioning

BEGIN;

-- Node definitions: persistent identity of what a node type/configuration IS
CREATE TABLE node_definitions (
    definition_id UUID PRIMARY KEY,
    node_type VARCHAR(255) NOT NULL,  -- executor, architect, verifier, etc
    provider_type VARCHAR(255),        -- openclaw, openai, anthropic, other
    runtime_type VARCHAR(255),         -- language/framework
    display_name VARCHAR(255) NOT NULL,
    lifecycle_state VARCHAR(50) DEFAULT 'candidate',  -- candidate, experimental, validated, restricted, disputed, deprecated, retired
    current_version_id UUID,           -- latest version
    current_applicable_scope TEXT,     -- domain/context where applicable
    supports_persistent BOOLEAN DEFAULT TRUE,
    supports_ephemeral BOOLEAN DEFAULT FALSE,
    requires_credentials BOOLEAN DEFAULT FALSE,
    estimated_resource_needs JSONB,    -- memory, cpu, network requirements
    definition_metadata JSONB,         -- extensible metadata
    provenance_id UUID REFERENCES learning_provenance(provenance_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    retired_at TIMESTAMPTZ
);

CREATE INDEX idx_node_definitions_type ON node_definitions(node_type);
CREATE INDEX idx_node_definitions_state ON node_definitions(lifecycle_state);
CREATE INDEX idx_node_definitions_provider ON node_definitions(provider_type);
CREATE INDEX idx_node_definitions_scope ON node_definitions USING GIN(definition_metadata);

-- Node definition versions: immutable snapshots
CREATE TABLE node_definition_versions (
    version_id UUID PRIMARY KEY,
    definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_number INT NOT NULL,
    parent_version_id UUID REFERENCES node_definition_versions(version_id),
    description TEXT,
    capabilities JSONB NOT NULL,      -- array of capability strings
    tool_requirements JSONB,           -- array of tools with versions
    model_reference VARCHAR(255),      -- model name/version if applicable
    execution_constraints JSONB,       -- resource/time constraints
    supported_task_types JSONB,        -- array of task type applicability
    domain_specialisations JSONB,      -- array of specialisation contexts
    execution_configuration JSONB,     -- provider-specific config
    version_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_version_per_definition UNIQUE(definition_id, version_number)
);

CREATE INDEX idx_node_def_versions_def ON node_definition_versions(definition_id);
CREATE INDEX idx_node_def_versions_parent ON node_definition_versions(parent_version_id);
CREATE INDEX idx_node_def_versions_capabilities ON node_definition_versions USING GIN(capabilities);

-- Node definition lineage: relationships between versions
CREATE TABLE node_definition_lineage (
    lineage_id UUID PRIMARY KEY,
    source_definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    source_version_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    target_definition_id UUID REFERENCES node_definitions(definition_id),
    target_version_id UUID REFERENCES node_definition_versions(version_id),
    relationship_type VARCHAR(50) NOT NULL,  -- derived_from, revises, specialises, generalises, supersedes, replaces, retired_from
    relationship_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_lineage_source ON node_definition_lineage(source_definition_id);
CREATE INDEX idx_lineage_target ON node_definition_lineage(target_definition_id);
CREATE INDEX idx_lineage_type ON node_definition_lineage(relationship_type);

-- Actual node instances: running/available nodes
CREATE TABLE node_instances (
    instance_id UUID PRIMARY KEY,
    definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    provider_endpoint VARCHAR(500),    -- connection reference if applicable
    runtime_location VARCHAR(255),     -- local, remote, vps, etc
    current_status VARCHAR(50) DEFAULT 'available',  -- available, busy, unavailable, error, retired
    capabilities_available JSONB,      -- actual available subset of definition capabilities
    health_score FLOAT DEFAULT 1.0,
    last_heartbeat TIMESTAMPTZ,
    creation_context JSONB,            -- how/why instance was created
    instance_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    retired_at TIMESTAMPTZ
);

CREATE INDEX idx_node_instances_def ON node_instances(definition_id);
CREATE INDEX idx_node_instances_status ON node_instances(current_status);
CREATE INDEX idx_node_instances_version ON node_instances(version_id);

-- Capability gaps: missing capabilities triggering evolution
CREATE TABLE capability_gaps (
    gap_id UUID PRIMARY KEY,
    gap_type VARCHAR(50) NOT NULL,     -- missing_capability, repeated_mismatch, repeated_failure
    required_capability VARCHAR(255) NOT NULL,
    task_type VARCHAR(255),
    domain_context VARCHAR(255),
    observation_count INT DEFAULT 1,
    first_observed_at TIMESTAMPTZ DEFAULT NOW(),
    last_observed_at TIMESTAMPTZ DEFAULT NOW(),
    evidence_ids UUID[],               -- link to outcomes/attempts that triggered gap
    gap_status VARCHAR(50) DEFAULT 'open',  -- open, proposed, addressed, retired
    gap_metadata JSONB,
    CONSTRAINT unique_gap UNIQUE(required_capability, task_type, domain_context)
);

CREATE INDEX idx_capability_gaps_type ON capability_gaps(gap_type);
CREATE INDEX idx_capability_gaps_capability ON capability_gaps(required_capability);
CREATE INDEX idx_capability_gaps_task_type ON capability_gaps(task_type);
CREATE INDEX idx_capability_gaps_status ON capability_gaps(gap_status);

-- Evolution proposals: triggered improvement suggestions
CREATE TABLE node_evolution_proposals (
    proposal_id UUID PRIMARY KEY,
    proposal_type VARCHAR(50) NOT NULL,  -- capability_addition, capability_removal, model_change, specialisation, deprecation, retirement
    triggering_evidence JSONB,         -- what prompted this
    triggering_gap_id UUID REFERENCES capability_gaps(gap_id),
    triggering_task_id UUID,
    triggering_outcome_id UUID,
    triggering_failure_count INT,
    existing_definition_id UUID REFERENCES node_definitions(definition_id),
    existing_version_id UUID REFERENCES node_definition_versions(version_id),
    proposed_change JSONB NOT NULL,
    expected_benefit TEXT,
    applicability_scope TEXT,
    constraints TEXT,
    proposed_definition_id UUID REFERENCES node_definitions(definition_id),  -- candidate if created
    proposal_status VARCHAR(50) DEFAULT 'proposed',  -- proposed, experimental, validated, rejected, retired
    rule_config_version_id UUID,       -- evolution rule version used
    rule_config_metadata JSONB,
    confidence_score FLOAT,
    evidence_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_proposals_type ON node_evolution_proposals(proposal_type);
CREATE INDEX idx_proposals_existing_def ON node_evolution_proposals(existing_definition_id);
CREATE INDEX idx_proposals_proposed_def ON node_evolution_proposals(proposed_definition_id);
CREATE INDEX idx_proposals_status ON node_evolution_proposals(proposal_status);
CREATE INDEX idx_proposals_trigger_gap ON node_evolution_proposals(triggering_gap_id);

-- Node configuration comparison: evidence from comparative execution
CREATE TABLE node_config_comparisons (
    comparison_id UUID PRIMARY KEY,
    definition_a_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_a_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    definition_b_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_b_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    task_type VARCHAR(255),
    domain_context VARCHAR(255),
    population_size INT,
    a_execution_count INT,
    b_execution_count INT,
    a_avg_quality_score FLOAT,
    b_avg_quality_score FLOAT,
    a_success_rate FLOAT,
    b_success_rate FLOAT,
    a_avg_execution_time FLOAT,
    b_avg_execution_time FLOAT,
    comparison_result VARCHAR(50),     -- a_superior, b_superior, equivalent, insufficient_evidence
    uncertainty_level VARCHAR(50),     -- high, moderate, low
    comparison_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_config_comp_a ON node_config_comparisons(definition_a_id);
CREATE INDEX idx_config_comp_b ON node_config_comparisons(definition_b_id);
CREATE INDEX idx_config_comp_task ON node_config_comparisons(task_type);

-- Node evolution decisions: promotion/restriction/retirement decisions
CREATE TABLE node_evolution_decisions (
    decision_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL REFERENCES node_evolution_proposals(proposal_id),
    definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    decision_type VARCHAR(50) NOT NULL,  -- promote, retain, restrict, dispute, retire
    decision_status VARCHAR(50) DEFAULT 'made',  -- made, applied
    rationale TEXT,
    evidence_summary JSONB,
    supporting_evidence_count INT,
    contradictory_evidence_count INT,
    contradictions_present BOOLEAN DEFAULT FALSE,
    decision_authority VARCHAR(255) DEFAULT 'system',
    requires_approval BOOLEAN DEFAULT FALSE,
    made_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    applied_by VARCHAR(255),
    decision_metadata JSONB
);

CREATE INDEX idx_evol_decisions_proposal ON node_evolution_decisions(proposal_id);
CREATE INDEX idx_evol_decisions_def ON node_evolution_decisions(definition_id);
CREATE INDEX idx_evol_decisions_type ON node_evolution_decisions(decision_type);
CREATE INDEX idx_evol_decisions_status ON node_evolution_decisions(decision_status);

-- Node evolution history: audit trail
CREATE TABLE node_evolution_history (
    history_id UUID PRIMARY KEY,
    definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    event_type VARCHAR(50) NOT NULL,   -- gap_detected, proposal_created, evaluation_started, validation_linked, decision_made, decision_applied, promoted, restricted, disputed, retired, superseded
    event_metadata JSONB,
    proposal_id UUID REFERENCES node_evolution_proposals(proposal_id),
    decision_id UUID REFERENCES node_evolution_decisions(decision_id),
    previous_state VARCHAR(50),
    new_state VARCHAR(50),
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_evol_history_def ON node_evolution_history(definition_id);
CREATE INDEX idx_evol_history_type ON node_evolution_history(event_type);
CREATE INDEX idx_evol_history_time ON node_evolution_history(recorded_at DESC);

-- Node instance creation requests: authority for spawning
CREATE TABLE node_instance_requests (
    request_id UUID PRIMARY KEY,
    definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
    version_id UUID NOT NULL REFERENCES node_definition_versions(version_id),
    request_type VARCHAR(50),          -- test, ephemeral_spawn, persistent_create
    request_reason TEXT,
    requested_by VARCHAR(255),
    request_context JSONB,
    request_status VARCHAR(50) DEFAULT 'requested',  -- requested, approved, provisioned, active, denied, cancelled
    approval_required BOOLEAN DEFAULT TRUE,
    approval_authority VARCHAR(255),
    approved_at TIMESTAMPTZ,
    provisioned_instance_id UUID REFERENCES node_instances(instance_id),
    request_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_instance_requests_def ON node_instance_requests(definition_id);
CREATE INDEX idx_instance_requests_status ON node_instance_requests(request_status);

-- Node evolution rule configuration: explicit controls
CREATE TABLE node_evolution_rule_config (
    config_id UUID PRIMARY KEY,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    rule_version INT DEFAULT 1,
    capability_gap_threshold INT DEFAULT 3,  -- failures before gap recorded
    min_gap_evidence INT DEFAULT 1,
    proposal_creation_enabled BOOLEAN DEFAULT TRUE,
    min_proposal_evidence INT DEFAULT 1,
    experiment_requirement_enabled BOOLEAN DEFAULT TRUE,
    validation_requirement_enabled BOOLEAN DEFAULT TRUE,
    retirement_enabled BOOLEAN DEFAULT TRUE,
    max_active_proposals INT DEFAULT 10,
    max_candidate_definitions INT DEFAULT 20,
    proposal_cooldown_seconds INT DEFAULT 3600,
    config_metadata JSONB,
    config_constraints JSONB
);

CREATE INDEX idx_evol_rules_active ON node_evolution_rule_config(active);

-- Deduplication registry for proposals
CREATE TABLE node_proposal_dedup_registry (
    registry_id UUID PRIMARY KEY,
    proposal_hash VARCHAR(255) UNIQUE NOT NULL,
    canonical_proposal_id UUID NOT NULL REFERENCES node_evolution_proposals(proposal_id),
    duplicate_count INT DEFAULT 1,
    last_attempted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_proposal_dedup_hash ON node_proposal_dedup_registry(proposal_hash);

-- Capability requirement tracking
CREATE TABLE capability_requirements (
    requirement_id UUID PRIMARY KEY,
    capability_name VARCHAR(255) NOT NULL,
    task_type VARCHAR(255),
    domain_context VARCHAR(255),
    requirement_strength VARCHAR(50) DEFAULT 'required',  -- required, strongly_preferred, preferred, optional
    observed_requirement_count INT DEFAULT 1,
    last_observed_at TIMESTAMPTZ DEFAULT NOW(),
    requirement_metadata JSONB,
    CONSTRAINT unique_capability_req UNIQUE(capability_name, task_type, domain_context)
);

CREATE INDEX idx_capability_reqs_name ON capability_requirements(capability_name);
CREATE INDEX idx_capability_reqs_task ON capability_requirements(task_type);

-- Ensure no orphaned node evolution data
ALTER TABLE node_definitions ADD FOREIGN KEY (current_version_id) REFERENCES node_definition_versions(version_id);

COMMIT;
