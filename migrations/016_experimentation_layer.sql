-- Section 16: Experimentation Layer
-- Controlled autonomous experimentation with competing strategies, hypotheses, and evidence collection

BEGIN;

-- Experiment identity and lifecycle
CREATE TABLE experiments (
    experiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis TEXT NOT NULL,
    objective TEXT NOT NULL,
    task_domain VARCHAR(100),
    
    -- Control and treatments
    control_strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    control_strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    
    -- Experiment configuration
    treatment_count INTEGER NOT NULL DEFAULT 1,
    metrics JSONB NOT NULL, -- [{metric_name, metric_type, threshold}]
    eligibility_criteria JSONB, -- Task/node requirements
    exclusion_criteria JSONB, -- What disqualifies a task
    
    -- Evidence requirements
    min_sample_size INTEGER NOT NULL DEFAULT 10,
    min_evidence_count INTEGER NOT NULL DEFAULT 5,
    evidence_threshold NUMERIC(3,2), -- Sufficiency threshold (0-1)
    
    -- Execution scope
    max_enrolled_tasks INTEGER NOT NULL DEFAULT 100,
    start_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_timestamp TIMESTAMPTZ,
    duration_limit_minutes INTEGER,
    
    -- Safety/governance
    safety_constraints JSONB, -- Constraints experiment must respect
    rule_version INTEGER NOT NULL DEFAULT 1,
    
    -- Status lifecycle
    status VARCHAR(30) NOT NULL DEFAULT 'proposed', -- proposed, approved, running, paused, completed, inconclusive, stopped, rejected, failed
    status_reason TEXT,
    
    -- Creator/governance
    creator_source VARCHAR(100), -- AI node identifier or system
    governance_approval BOOLEAN DEFAULT FALSE,
    governance_approver VARCHAR(100),
    
    -- Autonomous initiation
    autonomous_initiated BOOLEAN NOT NULL DEFAULT FALSE,
    autonomous_trigger_reason TEXT,
    autonomous_eligibility_check JSONB, -- Reason why autonomously eligible
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment lifecycle/status transitions (immutable history)
CREATE TABLE experiment_status_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    reason TEXT,
    evidence_summary JSONB, -- State at transition
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(100)
);

-- Treatment/variant definitions
CREATE TABLE experiment_arms (
    arm_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    arm_name VARCHAR(100) NOT NULL, -- "control", "treatment_A", "treatment_B", etc
    arm_type VARCHAR(30) NOT NULL, -- control, treatment
    
    -- Strategy/method for this arm
    strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    orchestration_config JSONB, -- Override orchestration rules for this arm
    
    -- Variant description
    variant_lineage_id UUID, -- Parent strategy if variant
    variant_description TEXT,
    
    -- Arm execution state
    enrolled_count INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Task enrollment in experiment arms (deterministic, immutable)
CREATE TABLE experiment_assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    arm_id UUID NOT NULL REFERENCES experiment_arms(arm_id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    
    -- Assignment determinism
    assignment_hash VARCHAR(128) NOT NULL, -- SHA256 of (experiment_id, task_id) for reproducibility
    
    -- Actual orchestration decision
    orchestration_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    assignment_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_started BOOLEAN NOT NULL DEFAULT FALSE,
    execution_started_at TIMESTAMPTZ,
    
    -- Enrollment protection
    status VARCHAR(30) NOT NULL DEFAULT 'enrolled', -- enrolled, executed, failed, excluded
    exclusion_reason TEXT,
    
    UNIQUE(experiment_id, task_id) -- Prevent duplicate enrollment
);

-- Raw observations (immutable)
CREATE TABLE experiment_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES experiment_assignments(assignment_id) ON DELETE CASCADE,
    arm_id UUID NOT NULL REFERENCES experiment_arms(arm_id) ON DELETE CASCADE,
    
    -- Execution evidence
    orchestration_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    strategy_used_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    worker_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
    
    -- Attempts/results
    attempts_count INTEGER NOT NULL DEFAULT 1,
    attempt_ids UUID[] NOT NULL, -- Array of attempt IDs
    final_outcome_status VARCHAR(30), -- success, failure, partial
    
    -- Metrics collected
    metric_values JSONB NOT NULL, -- {metric_name: value, ...}
    quality_score NUMERIC(3,2),
    execution_time_seconds INTEGER,
    
    -- Observation metadata
    observation_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verification_status VARCHAR(30), -- verified, unverified, disputed
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment analysis (immutable once complete)
CREATE TABLE experiment_analysis (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    
    -- Analysis metadata
    analysis_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analysis_version INTEGER NOT NULL DEFAULT 1,
    
    -- Sample information
    total_observations INTEGER NOT NULL,
    control_count INTEGER NOT NULL,
    treatment_count INTEGER NOT NULL,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    
    -- Metrics summary
    control_metric_summary JSONB NOT NULL, -- {metric: {mean, count, values}}
    treatment_metric_summary JSONB NOT NULL,
    
    -- Analysis result
    conclusion VARCHAR(50) NOT NULL, -- supportive, contradictory, neutral, insufficient_evidence
    effect_direction VARCHAR(20), -- positive, negative, none
    effect_size NUMERIC(5,3), -- Quantified difference
    evidence_sufficiency VARCHAR(30), -- high, adequate, low, insufficient
    confidence_level NUMERIC(3,2), -- 0-1
    
    -- Detailed findings
    supportive_evidence JSONB,
    contradictory_evidence JSONB,
    uncertainty_notes TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment conclusion (final state)
CREATE TABLE experiment_conclusions (
    conclusion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    analysis_id UUID REFERENCES experiment_analysis(analysis_id) ON DELETE SET NULL,
    
    -- Final determination
    conclusion_status VARCHAR(50) NOT NULL, -- conclusive_positive, conclusive_negative, inconclusive, insufficient_evidence
    conclusion_text TEXT,
    
    -- Evidence summary
    evidence_summary JSONB,
    raw_observation_count INTEGER,
    
    -- Next steps
    recommended_action VARCHAR(100), -- promote, reject, more_evidence, consult_human, etc
    rationale TEXT,
    
    -- Governance/promotion eligibility
    ready_for_promotion BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_rationale TEXT,
    
    concluded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Early stopping rules and triggers
CREATE TABLE experiment_early_stop_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    
    rule_type VARCHAR(50) NOT NULL, -- repeated_failure, safety_violation, impossible_execution, evidence_threshold
    
    -- Condition specification
    trigger_condition JSONB NOT NULL, -- {threshold, metric, count}
    
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Early stop trigger history
CREATE TABLE experiment_early_stop_triggers (
    trigger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    rule_id UUID REFERENCES experiment_early_stop_rules(rule_id) ON DELETE SET NULL,
    
    trigger_type VARCHAR(50) NOT NULL,
    trigger_evidence JSONB,
    stop_decision VARCHAR(50), -- stop, continue, escalate
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment opportunities for autonomous proposal
CREATE TABLE experiment_opportunities (
    opportunity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Opportunity type
    opportunity_type VARCHAR(50) NOT NULL, -- insufficient_evidence, conflicting_evidence, strategy_variant, repair_variant
    
    -- Context
    strategy_id_1 UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_id_2 UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    task_domain VARCHAR(100),
    
    -- Why this is an opportunity
    reason_text TEXT,
    evidence_gap JSONB, -- What's missing
    
    -- Autonomous eligibility
    eligible_for_autonomous_initiation BOOLEAN NOT NULL DEFAULT FALSE,
    autonomous_eligibility_reason TEXT,
    
    -- Status
    status VARCHAR(30) NOT NULL DEFAULT 'identified', -- identified, proposed, experiment_created, rejected
    experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE SET NULL,
    
    identified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment budget and resource limits
CREATE TABLE experiment_budget_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Limits
    max_active_experiments INTEGER NOT NULL DEFAULT 5,
    max_enrolled_tasks_global INTEGER NOT NULL DEFAULT 500,
    max_attempts_per_task INTEGER NOT NULL DEFAULT 3,
    max_failure_count INTEGER NOT NULL DEFAULT 20,
    
    -- Autonomous control
    allow_autonomous_initiation BOOLEAN NOT NULL DEFAULT TRUE,
    autonomous_priority_metric VARCHAR(50) DEFAULT 'evidence_gap',
    
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiment conflicts (simultaneous incompatible experiments)
CREATE TABLE experiment_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_1_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    experiment_2_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    
    conflict_type VARCHAR(50) NOT NULL, -- task_population_overlap, strategy_interference, resource_conflict
    conflict_severity VARCHAR(30), -- low, medium, high
    conflict_reason TEXT,
    
    conflict_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (experiment_1_id < experiment_2_id) -- Prevent duplicate records
);

-- Indices for performance
CREATE INDEX idx_experiments_status ON experiments(status);
CREATE INDEX idx_experiments_created ON experiments(created_at DESC);
CREATE INDEX idx_experiments_autonomous ON experiments(autonomous_initiated) WHERE autonomous_initiated = TRUE;

CREATE INDEX idx_experiment_arms_experiment ON experiment_arms(experiment_id);
CREATE INDEX idx_experiment_arms_type ON experiment_arms(arm_type);

CREATE INDEX idx_experiment_assignments_experiment ON experiment_assignments(experiment_id);
CREATE INDEX idx_experiment_assignments_arm ON experiment_assignments(arm_id);
CREATE INDEX idx_experiment_assignments_task ON experiment_assignments(task_id);
CREATE INDEX idx_experiment_assignments_status ON experiment_assignments(status);
CREATE UNIQUE INDEX idx_experiment_assignments_unique ON experiment_assignments(experiment_id, task_id);

CREATE INDEX idx_experiment_observations_experiment ON experiment_observations(experiment_id);
CREATE INDEX idx_experiment_observations_assignment ON experiment_observations(assignment_id);
CREATE INDEX idx_experiment_observations_arm ON experiment_observations(arm_id);
CREATE INDEX idx_experiment_observations_timestamp ON experiment_observations(observation_timestamp DESC);

CREATE INDEX idx_experiment_analysis_experiment ON experiment_analysis(experiment_id);
CREATE INDEX idx_experiment_analysis_timestamp ON experiment_analysis(analysis_timestamp DESC);

CREATE INDEX idx_experiment_conclusions_experiment ON experiment_conclusions(experiment_id);
CREATE INDEX idx_experiment_conclusions_status ON experiment_conclusions(conclusion_status);

CREATE INDEX idx_experiment_status_history_experiment ON experiment_status_history(experiment_id);
CREATE INDEX idx_experiment_status_history_time ON experiment_status_history(changed_at DESC);

CREATE INDEX idx_experiment_opportunities_type ON experiment_opportunities(opportunity_type);
CREATE INDEX idx_experiment_opportunities_eligible ON experiment_opportunities(eligible_for_autonomous_initiation);
CREATE INDEX idx_experiment_opportunities_status ON experiment_opportunities(status);

CREATE INDEX idx_experiment_conflicts_experiments ON experiment_conflicts(experiment_1_id, experiment_2_id);

-- Initialize default budget configuration
INSERT INTO experiment_budget_config (
    max_active_experiments,
    max_enrolled_tasks_global,
    max_attempts_per_task,
    max_failure_count,
    allow_autonomous_initiation,
    autonomous_priority_metric,
    active
) VALUES (
    5,
    500,
    3,
    20,
    TRUE,
    'evidence_gap',
    TRUE
);

COMMIT;
