-- Section 17: Validation / Promotion Layer
-- Immutable decision layer for evidence-driven promotion of learned strategies, methods, knowledge

BEGIN;

-- Validation candidates - persistent record of items eligible for promotion/restriction
CREATE TABLE validation_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Candidate identity
    candidate_type VARCHAR(50) NOT NULL, -- strategy, strategy_version, knowledge_entity, orchestration_config
    candidate_ref_id UUID NOT NULL, -- References strategies.strategy_id, etc.
    candidate_ref_type VARCHAR(50), -- Specific reference type within category
    candidate_name VARCHAR(200),
    
    -- Status tracking
    current_status VARCHAR(50) NOT NULL DEFAULT 'eligible', -- eligible, validation_requested, promoted, restricted, retired, disputed, superseded
    proposed_target_status VARCHAR(50), -- What we want to validate toward
    
    -- Scope/applicability
    domain_applicability VARCHAR(100), -- e.g., 'analysis_task', 'code_generation', etc.
    applicable_task_types JSONB, -- Array of task types or null for universal
    capability_requirements JSONB, -- Required node capabilities
    constraint_scope JSONB, -- Additional applicability constraints
    
    -- Provenance
    source_node_id UUID, -- Which node/context generated this candidate
    source_experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE SET NULL, -- If from Section 16
    source_operational_evidence BOOLEAN DEFAULT FALSE, -- If from live operational use
    
    -- Candidate lifecycle
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validation_requested_at TIMESTAMPTZ,
    last_validation_decision_id UUID, -- Link to most recent decision
    superseded_by_candidate_id UUID REFERENCES validation_candidates(candidate_id) ON DELETE SET NULL,
    
    -- Immutability
    is_immutable BOOLEAN NOT NULL DEFAULT TRUE,
    retired_at TIMESTAMPTZ
);

CREATE INDEX idx_validation_candidates_type ON validation_candidates(candidate_type);
CREATE INDEX idx_validation_candidates_status ON validation_candidates(current_status);
CREATE INDEX idx_validation_candidates_created ON validation_candidates(created_at DESC);
CREATE INDEX idx_validation_candidates_experiment ON validation_candidates(source_experiment_id);

-- Supporting evidence for validation candidates
CREATE TABLE validation_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    -- Evidence classification
    evidence_type VARCHAR(50) NOT NULL, -- experimental_supportive, experimental_contradictory, operational, cross_node
    evidence_category VARCHAR(50), -- supportive, contradictory, neutral, insufficient
    
    -- Evidence sources
    source_experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE SET NULL,
    source_experiment_analysis_id UUID REFERENCES experiment_analysis(analysis_id) ON DELETE SET NULL,
    source_experiment_arm_id UUID, -- Which arm if from experiment
    source_operational_outcome_id UUID, -- If from real operational execution
    source_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
    cross_node_reproduced BOOLEAN DEFAULT FALSE, -- Whether same result on different nodes
    
    -- Evidence quality
    confidence_score NUMERIC(3,2), -- 0-1
    evidence_strength NUMERIC(3,2), -- 0-1 how compelling
    supporting_observation_count INTEGER, -- Number of supporting observations
    contradictory_observation_count INTEGER, -- Number of contradicting observations
    
    -- Evidence metadata
    evidence_summary TEXT,
    evidence_detail JSONB, -- Rich evidence content
    
    -- Immutability
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evidence_timestamp TIMESTAMPTZ -- When evidence was actually generated
);

CREATE INDEX idx_validation_evidence_candidate ON validation_evidence(candidate_id);
CREATE INDEX idx_validation_evidence_type ON validation_evidence(evidence_type);
CREATE INDEX idx_validation_evidence_source_experiment ON validation_evidence(source_experiment_id);
CREATE INDEX idx_validation_evidence_source_node ON validation_evidence(source_node_id);

-- Eligibility assessment - recorded check before validation
CREATE TABLE validation_eligibility (
    eligibility_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    -- Eligibility criteria
    candidate_exists BOOLEAN NOT NULL,
    evidence_count_sufficient BOOLEAN NOT NULL,
    min_evidence_count_required INTEGER,
    actual_evidence_count INTEGER,
    
    -- Evidence checks
    experimental_results_complete BOOLEAN,
    operational_evidence_valid BOOLEAN,
    provenance_exists BOOLEAN,
    contradictory_evidence_considered BOOLEAN,
    cross_node_evidence_considered BOOLEAN,
    
    -- Status checks
    not_already_retired BOOLEAN,
    not_already_superseded BOOLEAN,
    constraints_allow_evaluation BOOLEAN,
    governance_allows_evaluation BOOLEAN,
    
    -- Eligibility decision
    is_eligible BOOLEAN NOT NULL,
    ineligibility_reason TEXT, -- If not eligible
    ineligibility_detail JSONB,
    
    -- Evaluation
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluated_by VARCHAR(100) -- System or explicit authority
);

CREATE INDEX idx_validation_eligibility_candidate ON validation_eligibility(candidate_id);
CREATE INDEX idx_validation_eligibility_result ON validation_eligibility(is_eligible);

-- Evidence sufficiency assessment
CREATE TABLE validation_evidence_sufficiency (
    sufficiency_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    -- Thresholds applied
    rule_config_version_id UUID, -- Version of rule/config used
    
    -- Sample requirements
    min_supporting_observations INTEGER,
    actual_supporting_observations INTEGER,
    min_operational_evidence INTEGER,
    actual_operational_evidence INTEGER,
    
    -- Quality requirements
    min_average_confidence NUMERIC(3,2),
    actual_average_confidence NUMERIC(3,2),
    min_evidence_strength NUMERIC(3,2),
    actual_evidence_strength NUMERIC(3,2),
    
    -- Independence
    independent_node_requirement INTEGER, -- 0 = any, 1+ = number of distinct nodes required
    distinct_nodes_supporting INTEGER,
    independent_requirement_met BOOLEAN,
    
    -- Contradiction tolerance
    max_contradictions_allowed INTEGER,
    actual_contradictions INTEGER,
    contradiction_severity_avg NUMERIC(3,2),
    
    -- Recency
    max_age_days INTEGER,
    oldest_supporting_evidence_days INTEGER,
    recency_acceptable BOOLEAN,
    
    -- Applicability match
    applicability_match_required BOOLEAN,
    applicability_match_score NUMERIC(3,2),
    
    -- Overall sufficiency
    evidence_sufficient BOOLEAN NOT NULL,
    sufficiency_level VARCHAR(30), -- high, adequate, low, insufficient
    sufficiency_detail JSONB,
    
    -- Assessment
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_sufficiency_candidate ON validation_evidence_sufficiency(candidate_id);
CREATE INDEX idx_validation_sufficiency_result ON validation_evidence_sufficiency(evidence_sufficient);

-- Immutable validation decisions
CREATE TABLE validation_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    -- Decision details
    decision_type VARCHAR(50) NOT NULL, -- promote, retain_candidate, strengthen, weaken, restrict, dispute, reject, retire, repeat_experiment, insufficient_evidence
    decision_status VARCHAR(30) NOT NULL DEFAULT 'made', -- made, applied, superseded, under_review
    
    -- Evidence summary
    supporting_evidence_count INTEGER,
    contradictory_evidence_count INTEGER,
    neutral_evidence_count INTEGER,
    evidence_summary JSONB,
    
    -- Sufficiency
    evidence_sufficiency_level VARCHAR(30), -- high, adequate, low, insufficient
    confidence_level NUMERIC(3,2),
    
    -- Contradiction handling
    contradictions_present BOOLEAN DEFAULT FALSE,
    contradiction_severity VARCHAR(30), -- low, medium, high
    contradiction_handling VARCHAR(100), -- How contradictions were treated
    
    -- Applicability
    applicable_scope JSONB, -- What scope this decision applies to
    restricted_from_scope JSONB, -- If restricted, what it's NOT validated for
    
    -- Rule version
    rule_config_version_id UUID,
    rule_description TEXT,
    
    -- Decision rationale
    rationale TEXT NOT NULL,
    decision_factors JSONB, -- Structured factors influencing decision
    alternatives_considered JSONB, -- Other possible decisions and why not chosen
    
    -- Authority
    decision_authority VARCHAR(100), -- system, automatic (if enabled), governance, admin, etc.
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_by VARCHAR(100),
    approval_timestamp TIMESTAMPTZ,
    
    -- Application tracking
    applied_at TIMESTAMPTZ,
    applied_by VARCHAR(100),
    applied_to_state_version VARCHAR(50), -- What system state version this was applied to
    
    -- Reversibility
    can_be_reversed BOOLEAN DEFAULT TRUE,
    reversed_by_decision_id UUID REFERENCES validation_decisions(decision_id) ON DELETE SET NULL,
    
    -- Immutability
    made_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    made_by VARCHAR(100),
    
    -- Cross-node
    cross_node_evidence_required BOOLEAN DEFAULT FALSE,
    cross_node_evidence_met BOOLEAN
);

CREATE INDEX idx_validation_decisions_candidate ON validation_decisions(candidate_id);
CREATE INDEX idx_validation_decisions_type ON validation_decisions(decision_type);
CREATE INDEX idx_validation_decisions_status ON validation_decisions(decision_status);
CREATE INDEX idx_validation_decisions_made ON validation_decisions(made_at DESC);
CREATE INDEX idx_validation_decisions_applied ON validation_decisions(applied_at DESC);

-- Repeat experiment requests - when validation decides more experimentation needed
CREATE TABLE validation_repeat_experiments (
    repeat_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    validation_decision_id UUID NOT NULL REFERENCES validation_decisions(decision_id) ON DELETE CASCADE,
    
    -- Experiment request
    experiment_hypothesis TEXT,
    experiment_objective TEXT,
    metrics JSONB,
    min_sample_size INTEGER,
    max_enrolled_tasks INTEGER,
    
    -- Link to actual experiment if created
    created_experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE SET NULL,
    
    -- Status
    request_status VARCHAR(30) NOT NULL DEFAULT 'requested', -- requested, created, completed, cancelled
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    -- Justification
    reason_for_repeat TEXT,
    evidence_gaps JSONB
);

CREATE INDEX idx_repeat_experiments_candidate ON validation_repeat_experiments(candidate_id);
CREATE INDEX idx_repeat_experiments_decision ON validation_repeat_experiments(validation_decision_id);
CREATE INDEX idx_repeat_experiments_status ON validation_repeat_experiments(request_status);

-- Validation rule/config versions - inspectable and versioned
CREATE TABLE validation_rule_configs (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_version_id UUID DEFAULT gen_random_uuid(),
    
    -- Rule identity
    rule_name VARCHAR(100),
    rule_description TEXT,
    candidate_type VARCHAR(50), -- What type of candidates this rule applies to
    
    -- Thresholds
    min_supporting_observations INTEGER DEFAULT 3,
    min_operational_evidence INTEGER DEFAULT 1,
    min_average_confidence NUMERIC(3,2) DEFAULT 0.70,
    min_evidence_strength NUMERIC(3,2) DEFAULT 0.60,
    independent_node_requirement INTEGER DEFAULT 0, -- 0 = any, 1+ = number of distinct nodes
    max_contradictions_allowed INTEGER DEFAULT 1,
    max_age_days INTEGER, -- NULL = no recency requirement
    
    -- Flags
    require_applicability_match BOOLEAN DEFAULT TRUE,
    require_experimental_evidence BOOLEAN DEFAULT FALSE,
    require_operational_evidence BOOLEAN DEFAULT FALSE,
    allow_automatic_promotion BOOLEAN DEFAULT FALSE, -- Critical: default conservative
    allow_automatic_restriction BOOLEAN DEFAULT FALSE,
    allow_automatic_retirement BOOLEAN DEFAULT FALSE,
    
    -- Contradiction handling
    contradiction_handling VARCHAR(50) DEFAULT 'dispute', -- dispute, restrict, repeat_experiment, manual_review
    
    -- Repeat experiment config
    enable_repeat_experiments BOOLEAN DEFAULT TRUE,
    repeat_when_insufficient BOOLEAN DEFAULT TRUE,
    repeat_when_conflicting BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version_number INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_validation_rules_type ON validation_rule_configs(candidate_type);
CREATE INDEX idx_validation_rules_active ON validation_rule_configs(active);
CREATE INDEX idx_validation_rules_version ON validation_rule_configs(config_version_id);

-- Insert default conservative rule config
INSERT INTO validation_rule_configs (
    rule_name, rule_description, candidate_type,
    min_supporting_observations, min_operational_evidence,
    min_average_confidence, min_evidence_strength,
    independent_node_requirement, max_contradictions_allowed,
    allow_automatic_promotion,
    contradiction_handling, enable_repeat_experiments
) VALUES (
    'default_strategy_promotion',
    'Conservative default rule for strategy promotion',
    'strategy',
    5, 2, 0.75, 0.70, 1, 0,
    FALSE,
    'dispute', TRUE
);

-- Validation history - complete audit trail
CREATE TABLE validation_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    -- What happened
    event_type VARCHAR(50) NOT NULL, -- candidate_created, validation_requested, eligibility_checked, evidence_assembled, decision_made, decision_applied, state_changed, superseded
    event_detail JSONB,
    
    -- Related entities
    decision_id UUID REFERENCES validation_decisions(decision_id) ON DELETE SET NULL,
    previous_status VARCHAR(50),
    new_status VARCHAR(50),
    
    -- Tracking
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recorded_by VARCHAR(100)
);

CREATE INDEX idx_validation_history_candidate ON validation_history(candidate_id);
CREATE INDEX idx_validation_history_event ON validation_history(event_type);
CREATE INDEX idx_validation_history_time ON validation_history(recorded_at DESC);

-- Deduplication registry - prevent duplicate validation of same candidate
CREATE TABLE validation_dedup_registry (
    dedup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES validation_candidates(candidate_id) ON DELETE CASCADE,
    
    candidate_hash VARCHAR(128), -- SHA256 of candidate identity
    canonical_candidate_id UUID, -- If already validated, reference to canonical
    validation_attempt_count INTEGER DEFAULT 0,
    
    last_attempted_at TIMESTAMPTZ,
    first_validated_at TIMESTAMPTZ
);

CREATE INDEX idx_dedup_candidate ON validation_dedup_registry(candidate_id);
CREATE INDEX idx_dedup_hash ON validation_dedup_registry(candidate_hash);

COMMIT;
