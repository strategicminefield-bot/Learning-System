-- Section 15: Adaptive Orchestration
-- Implements evidence-based orchestration decision-making that influences actual task execution

BEGIN;

-- Orchestration decision records
CREATE TABLE orchestration_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES assignments(assignment_id) ON DELETE SET NULL,
    decision_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context_considered JSONB NOT NULL, -- Task metadata, constraints, relevance
    
    -- Candidate strategies
    strategy_candidates JSONB NOT NULL, -- Array of {strategy_id, version_id, effectiveness, evidence_count, confidence}
    strategy_selected UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_version_selected UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    strategy_rationale TEXT,
    
    -- Candidate workers
    worker_candidates JSONB, -- Array of {node_id, capabilities, availability, evidence, applicability}
    worker_selected UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
    worker_rationale TEXT,
    
    -- Plan generation
    execution_plan JSONB NOT NULL, -- Structured plan with ordered steps, constraints, expectations
    plan_constraints JSONB, -- Applicable constraints for this decision
    plan_fallback JSONB, -- Known fallback/recovery approach
    
    -- Evidence evaluation
    evidence_sufficiency TEXT NOT NULL DEFAULT 'adequate', -- high, adequate, low, insufficient
    evidence_summary JSONB, -- {strategy_evidence_count, negative_evidence_items, cross_node_evidence, contradictions}
    
    -- Decision metadata
    confidence_score NUMERIC(3,2) NOT NULL DEFAULT 0.50 CHECK (confidence_score >= 0 AND confidence_score <= 1.00),
    decision_rationale JSONB NOT NULL, -- {why_selected, why_alternatives_rejected, uncertainty, fallback_reason}
    
    -- Attempted execution
    attempts_made INTEGER NOT NULL DEFAULT 0,
    final_outcome_status VARCHAR(20), -- pending, success, failure, partial, abandoned
    final_outcome_id UUID REFERENCES task_outcomes(outcome_id) ON DELETE SET NULL,
    
    -- Replanning tracking
    replanned_from UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    replanned_to UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    replan_trigger VARCHAR(100), -- worker_unavailable, strategy_failed, constraint_conflict, evidence_updated
    
    -- Orchestration rule version
    rule_version INTEGER NOT NULL DEFAULT 1,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Candidate generation trace
CREATE TABLE orchestration_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES orchestration_decisions(decision_id) ON DELETE CASCADE,
    candidate_type VARCHAR(20) NOT NULL, -- strategy, worker, fallback
    
    -- Strategy candidates
    strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    strategy_effectiveness NUMERIC(3,2),
    strategy_evidence_count INTEGER,
    strategy_confidence NUMERIC(3,2),
    strategy_negative_evidence JSONB, -- Items suggesting rejection
    strategy_applicability_score NUMERIC(3,2),
    
    -- Worker candidates
    node_id UUID REFERENCES nodes(node_id) ON DELETE SET NULL,
    node_capabilities JSONB, -- Required vs available
    node_availability VARCHAR(20), -- available, busy, unavailable
    node_health_score NUMERIC(3,2),
    node_applicability_score NUMERIC(3,2),
    
    -- Fallback/default
    fallback_reason TEXT, -- insufficient_evidence, no_strategy, worker_unavailable, etc.
    fallback_method JSONB,
    
    -- Evaluation
    evaluated BOOLEAN NOT NULL DEFAULT FALSE,
    evaluation_timestamp TIMESTAMPTZ,
    included_in_ranking BOOLEAN NOT NULL DEFAULT TRUE,
    rejection_reason TEXT,
    
    -- Candidate ranking
    candidate_rank INTEGER,
    selection_score NUMERIC(3,2),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Evidence-based selection audit
CREATE TABLE orchestration_evidence_evaluation (
    evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES orchestration_decisions(decision_id) ON DELETE CASCADE,
    candidate_id UUID REFERENCES orchestration_candidates(candidate_id) ON DELETE SET NULL,
    
    evidence_dimension VARCHAR(50) NOT NULL, -- applicability, effectiveness, validation, failures, repairs, availability, constraints, contradictions, cross_node
    evidence_items JSONB NOT NULL, -- Array of {type, value, source, confidence}
    
    dimension_weight NUMERIC(3,2),
    dimension_score NUMERIC(3,2),
    
    supporting_evidence JSONB, -- Favored this candidate
    rejecting_evidence JSONB, -- Argued against this candidate
    conflicting_evidence JSONB, -- Contradictory evidence
    
    evaluation_order INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Execution plan structure
CREATE TABLE orchestration_plans (
    plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES orchestration_decisions(decision_id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES assignments(assignment_id) ON DELETE SET NULL,
    
    strategy_id UUID REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    strategy_version_id UUID REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    
    ordered_steps JSONB NOT NULL, -- [{step_order, method, expected_output, time_estimate}]
    context_guidance JSONB, -- Retrieved context applied to execution
    constraints JSONB, -- Task-level, strategy-level constraints
    
    expected_verification JSONB, -- Verification criteria for success
    fallback_path JSONB, -- Known repair/alternate method
    known_recovery_strategies JSONB, -- Available recovery options
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Execution outcome feedback
CREATE TABLE orchestration_outcomes (
    outcome_evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES orchestration_decisions(decision_id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES assignments(assignment_id) ON DELETE SET NULL,
    task_id UUID REFERENCES tasks(task_id) ON DELETE SET NULL,
    
    actual_outcome_status VARCHAR(20) NOT NULL, -- success, failure, partial, abandoned
    actual_outcome_id UUID REFERENCES task_outcomes(outcome_id) ON DELETE SET NULL,
    
    -- Execution metrics
    attempts_required INTEGER NOT NULL,
    repairs_used JSONB, -- Array of repair applications
    actual_execution_time_seconds INTEGER,
    actual_quality_score NUMERIC(3,2),
    
    -- Strategy evaluation
    strategy_performed_as_expected BOOLEAN,
    strategy_effectiveness_observed NUMERIC(3,2),
    strategy_failure_reason TEXT,
    strategy_repair_successful BOOLEAN,
    
    -- Worker evaluation
    worker_capable BOOLEAN,
    worker_available_when_needed BOOLEAN,
    worker_quality_score NUMERIC(3,2),
    worker_performance_vs_predicted NUMERIC(3,2), -- Positive/negative delta
    
    -- Plan evaluation
    plan_accurate BOOLEAN,
    plan_followed BOOLEAN,
    plan_modifications JSONB, -- Actual deviations from plan
    
    -- Outcome feedback
    orchestration_decision_quality NUMERIC(3,2), -- How good was the decision
    orchestration_correct BOOLEAN, -- Would same decision succeed again?
    orchestration_improvement_notes TEXT,
    
    -- Evidence for future orchestration
    evidence_for_strategy_learning JSONB, -- {success, failure, insufficient}
    evidence_for_worker_learning JSONB, -- {capable, unavailable, quality}
    evidence_for_constraint_learning JSONB, -- Constraint effectiveness
    evidence_for_repair_learning JSONB, -- Repair effectiveness
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Replanning decision trigger
CREATE TABLE orchestration_replan_triggers (
    trigger_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_decision_id UUID NOT NULL REFERENCES orchestration_decisions(decision_id) ON DELETE CASCADE,
    new_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    
    trigger_type VARCHAR(50) NOT NULL, -- failed_attempt, worker_unavailable, strategy_invalidated, constraint_conflict, evidence_updated
    trigger_reason TEXT,
    
    attempt_number INTEGER,
    failure_details JSONB, -- Specific failure info
    
    replan_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replan_approved BOOLEAN NOT NULL DEFAULT FALSE,
    approval_rationale TEXT
);

-- Fallback/default orchestration paths
CREATE TABLE orchestration_fallback_registry (
    fallback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type VARCHAR(100),
    context_conditions JSONB, -- When to use this fallback
    
    fallback_type VARCHAR(50) NOT NULL, -- default, timeout, unavailable, insufficient_evidence
    fallback_method JSONB NOT NULL, -- Execution approach
    fallback_strategy VARCHAR(100), -- Name/description
    
    success_rate_observed NUMERIC(3,2),
    times_used INTEGER NOT NULL DEFAULT 0,
    last_used TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orchestration rule configuration
CREATE TABLE orchestration_rule_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_version INTEGER NOT NULL UNIQUE,
    
    -- Selection thresholds
    min_strategy_effectiveness NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    min_strategy_confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    min_worker_applicability NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    
    -- Evidence requirements
    min_evidence_count_high_confidence INTEGER NOT NULL DEFAULT 5,
    min_evidence_count_adequate_confidence INTEGER NOT NULL DEFAULT 2,
    
    -- Constraint handling
    explicit_constraints_override_learned_preference BOOLEAN NOT NULL DEFAULT TRUE,
    respect_negative_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Replanning limits
    max_replan_attempts INTEGER NOT NULL DEFAULT 3,
    replan_backoff_ms INTEGER NOT NULL DEFAULT 1000,
    
    -- Conflict resolution
    conflicting_evidence_default_strategy VARCHAR(50) NOT NULL DEFAULT 'conservative',
    
    -- Worker selection
    prefer_worker_health_over_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    require_worker_availability BOOLEAN NOT NULL DEFAULT TRUE,
    
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotency registry
CREATE TABLE orchestration_idempotency_registry (
    registry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    request_hash VARCHAR(128) NOT NULL UNIQUE,
    canonical_decision_id UUID REFERENCES orchestration_decisions(decision_id) ON DELETE SET NULL,
    is_retry BOOLEAN NOT NULL DEFAULT FALSE,
    retry_attempt_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_orchestration_decisions_task ON orchestration_decisions(task_id);
CREATE INDEX idx_orchestration_decisions_assignment ON orchestration_decisions(assignment_id);
CREATE INDEX idx_orchestration_decisions_strategy ON orchestration_decisions(strategy_selected);
CREATE INDEX idx_orchestration_decisions_worker ON orchestration_decisions(worker_selected);
CREATE INDEX idx_orchestration_decisions_status ON orchestration_decisions(final_outcome_status);
CREATE INDEX idx_orchestration_decisions_time ON orchestration_decisions(created_at DESC);
CREATE INDEX idx_orchestration_decisions_rule_version ON orchestration_decisions(rule_version);

CREATE INDEX idx_orchestration_candidates_decision ON orchestration_candidates(decision_id);
CREATE INDEX idx_orchestration_candidates_strategy ON orchestration_candidates(strategy_id);
CREATE INDEX idx_orchestration_candidates_node ON orchestration_candidates(node_id);
CREATE INDEX idx_orchestration_candidates_rank ON orchestration_candidates(candidate_rank);

CREATE INDEX idx_orchestration_evidence_decision ON orchestration_evidence_evaluation(decision_id);
CREATE INDEX idx_orchestration_evidence_dimension ON orchestration_evidence_evaluation(evidence_dimension);

CREATE INDEX idx_orchestration_plans_decision ON orchestration_plans(decision_id);
CREATE INDEX idx_orchestration_plans_assignment ON orchestration_plans(assignment_id);

CREATE INDEX idx_orchestration_outcomes_decision ON orchestration_outcomes(decision_id);
CREATE INDEX idx_orchestration_outcomes_status ON orchestration_outcomes(actual_outcome_status);
CREATE INDEX idx_orchestration_outcomes_time ON orchestration_outcomes(created_at DESC);

CREATE INDEX idx_orchestration_replan_original ON orchestration_replan_triggers(original_decision_id);
CREATE INDEX idx_orchestration_replan_new ON orchestration_replan_triggers(new_decision_id);
CREATE INDEX idx_orchestration_replan_type ON orchestration_replan_triggers(trigger_type);

CREATE INDEX idx_orchestration_fallback_registry_type ON orchestration_fallback_registry(fallback_type);
CREATE INDEX idx_orchestration_fallback_registry_task ON orchestration_fallback_registry(task_type);

CREATE INDEX idx_orchestration_idempotency_task ON orchestration_idempotency_registry(task_id);
CREATE INDEX idx_orchestration_idempotency_hash ON orchestration_idempotency_registry(request_hash);

-- Initialize default rule configuration
INSERT INTO orchestration_rule_config (
    rule_version,
    min_strategy_effectiveness,
    min_strategy_confidence,
    min_worker_applicability,
    min_evidence_count_high_confidence,
    min_evidence_count_adequate_confidence,
    explicit_constraints_override_learned_preference,
    respect_negative_evidence,
    max_replan_attempts,
    replan_backoff_ms,
    conflicting_evidence_default_strategy,
    prefer_worker_health_over_evidence,
    require_worker_availability,
    active
) VALUES (
    1,
    0.50, 0.50, 0.50,
    5, 2,
    TRUE, TRUE,
    3, 1000,
    'conservative',
    TRUE, TRUE,
    TRUE
);

COMMIT;
