-- Section 16: Experimentation Layer (Fixed)
BEGIN;

CREATE TABLE experiments (
    experiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis TEXT NOT NULL,
    objective TEXT NOT NULL,
    task_domain VARCHAR(100),
    control_strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    control_strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    treatment_count INTEGER NOT NULL DEFAULT 1,
    metrics JSONB NOT NULL,
    eligibility_criteria JSONB,
    exclusion_criteria JSONB,
    min_sample_size INTEGER NOT NULL DEFAULT 10,
    min_evidence_count INTEGER NOT NULL DEFAULT 5,
    evidence_threshold NUMERIC(3,2),
    max_enrolled_tasks INTEGER NOT NULL DEFAULT 100,
    start_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_timestamp TIMESTAMPTZ,
    duration_limit_minutes INTEGER,
    safety_constraints JSONB,
    rule_version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(30) NOT NULL DEFAULT 'proposed',
    status_reason TEXT,
    creator_source VARCHAR(100),
    governance_approval BOOLEAN DEFAULT FALSE,
    governance_approver VARCHAR(100),
    autonomous_initiated BOOLEAN NOT NULL DEFAULT FALSE,
    autonomous_trigger_reason TEXT,
    autonomous_eligibility_check JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_status_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    reason TEXT,
    evidence_summary JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(100)
);

CREATE TABLE experiment_arms (
    arm_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    arm_name VARCHAR(100) NOT NULL,
    arm_type VARCHAR(30) NOT NULL,
    strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    orchestration_config JSONB,
    variant_lineage_id UUID,
    variant_description TEXT,
    enrolled_count INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    arm_id UUID NOT NULL REFERENCES experiment_arms(arm_id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    assignment_hash VARCHAR(128) NOT NULL,
    orchestration_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    assignment_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_started BOOLEAN NOT NULL DEFAULT FALSE,
    execution_started_at TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'enrolled',
    exclusion_reason TEXT,
    UNIQUE(experiment_id, task_id)
);

CREATE TABLE experiment_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES experiment_assignments(assignment_id) ON DELETE CASCADE,
    arm_id UUID NOT NULL REFERENCES experiment_arms(arm_id) ON DELETE CASCADE,
    orchestration_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    strategy_used_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    worker_node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
    attempts_count INTEGER NOT NULL DEFAULT 1,
    attempt_ids UUID[] DEFAULT ARRAY[]::UUID[],
    final_outcome_status VARCHAR(30),
    metric_values JSONB NOT NULL,
    quality_score NUMERIC(3,2),
    execution_time_seconds INTEGER,
    observation_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verification_status VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_analysis (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    analysis_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analysis_version INTEGER NOT NULL DEFAULT 1,
    total_observations INTEGER NOT NULL,
    control_count INTEGER NOT NULL,
    treatment_count INTEGER NOT NULL,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    control_metric_summary JSONB NOT NULL,
    treatment_metric_summary JSONB NOT NULL,
    conclusion VARCHAR(50) NOT NULL,
    effect_direction VARCHAR(20),
    effect_size NUMERIC(5,3),
    evidence_sufficiency VARCHAR(30),
    confidence_level NUMERIC(3,2),
    supportive_evidence JSONB,
    contradictory_evidence JSONB,
    uncertainty_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_conclusions (
    conclusion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    analysis_id UUID REFERENCES experiment_analysis(analysis_id) ON DELETE SET NULL,
    conclusion_status VARCHAR(50) NOT NULL,
    conclusion_text TEXT,
    evidence_summary JSONB,
    raw_observation_count INTEGER,
    recommended_action VARCHAR(100),
    rationale TEXT,
    ready_for_promotion BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_rationale TEXT,
    concluded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_early_stop_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    rule_type VARCHAR(50) NOT NULL,
    trigger_condition JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_early_stop_triggers (
    trigger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    rule_id UUID REFERENCES experiment_early_stop_rules(rule_id) ON DELETE SET NULL,
    trigger_type VARCHAR(50) NOT NULL,
    trigger_evidence JSONB,
    stop_decision VARCHAR(50),
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_opportunities (
    opportunity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_type VARCHAR(50) NOT NULL,
    strategy_id_1 UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_id_2 UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    task_domain VARCHAR(100),
    reason_text TEXT,
    evidence_gap JSONB,
    eligible_for_autonomous_initiation BOOLEAN NOT NULL DEFAULT FALSE,
    autonomous_eligibility_reason TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'identified',
    experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE SET NULL,
    identified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_budget_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    max_active_experiments INTEGER NOT NULL DEFAULT 5,
    max_enrolled_tasks_global INTEGER NOT NULL DEFAULT 500,
    max_attempts_per_task INTEGER NOT NULL DEFAULT 3,
    max_failure_count INTEGER NOT NULL DEFAULT 20,
    allow_autonomous_initiation BOOLEAN NOT NULL DEFAULT TRUE,
    autonomous_priority_metric VARCHAR(50) DEFAULT 'evidence_gap',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE experiment_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_1_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    experiment_2_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
    conflict_type VARCHAR(50) NOT NULL,
    conflict_severity VARCHAR(30),
    conflict_reason TEXT,
    conflict_detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (experiment_1_id < experiment_2_id)
);

CREATE INDEX idx_experiments_status ON experiments(status);
CREATE INDEX idx_experiment_arms_experiment ON experiment_arms(experiment_id);
CREATE INDEX idx_experiment_assignments_experiment ON experiment_assignments(experiment_id);
CREATE INDEX idx_experiment_observations_experiment ON experiment_observations(experiment_id);
CREATE INDEX idx_experiment_analysis_experiment ON experiment_analysis(experiment_id);
CREATE INDEX idx_experiment_conclusions_experiment ON experiment_conclusions(experiment_id);
CREATE INDEX idx_experiment_opportunities_type ON experiment_opportunities(opportunity_type);

INSERT INTO experiment_budget_config (max_active_experiments, max_enrolled_tasks_global, max_attempts_per_task, max_failure_count, allow_autonomous_initiation) VALUES (5, 500, 3, 20, TRUE);

COMMIT;
