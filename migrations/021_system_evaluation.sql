-- Migration 021: System-Level Evaluation Layer
-- 
-- Adds persistent system evaluation capability to measure organisational effectiveness.
-- Evaluates against real evidence from Sections 2-20 without independently modifying production.

-- System evaluation runs: Track evaluation sessions
CREATE TABLE IF NOT EXISTS system_evaluation_runs (
    evaluation_id UUID PRIMARY KEY,
    evaluation_type VARCHAR(100) NOT NULL,  -- baseline, comparison, trend, subsystem, change_impact, etc.
    status VARCHAR(50) NOT NULL DEFAULT 'created',  -- created, collecting, evaluating, completed, insufficient_evidence, failed
    evaluation_rule_version INT NOT NULL,
    population_definition JSONB NOT NULL,
    scope VARCHAR(100),
    time_window_start TIMESTAMP WITH TIME ZONE,
    time_window_end TIMESTAMP WITH TIME ZONE,
    baseline_definition JSONB,
    comparison_definition JSONB,
    data_cutoff_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    trigger_source VARCHAR(100),
    initiating_actor_type VARCHAR(50),
    initiating_actor_reference VARCHAR(255),
    result JSONB,
    conclusion VARCHAR(100),
    evidence_sufficiency VARCHAR(50),
    limitations TEXT,
    provenance JSONB
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status ON system_evaluation_runs(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_type ON system_evaluation_runs(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created ON system_evaluation_runs(created_at DESC);

-- Evaluation populations: Persist population definitions for comparability
CREATE TABLE IF NOT EXISTS system_evaluation_populations (
    population_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    population_name VARCHAR(255),
    population_type VARCHAR(100),  -- task, strategy, node, experiment, etc.
    definition JSONB NOT NULL,
    dimension_filters JSONB,  -- e.g., {"task_type": "optimization", "domain": "learning"}
    count BIGINT,
    sample_count BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_populations_evaluation ON system_evaluation_populations(evaluation_id);

-- Baselines: Persist reference/comparison baselines
CREATE TABLE IF NOT EXISTS system_evaluation_baselines (
    baseline_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    baseline_type VARCHAR(100),  -- historical, frozen, control, pre_change, explicit, etc.
    baseline_identity JSONB NOT NULL,
    selection_method VARCHAR(100),
    time_window_start TIMESTAMP WITH TIME ZONE,
    time_window_end TIMESTAMP WITH TIME ZONE,
    population_id UUID REFERENCES system_evaluation_populations(population_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_baselines_evaluation ON system_evaluation_baselines(evaluation_id);

-- Core metrics: Calculated from authoritative evidence
CREATE TABLE IF NOT EXISTS system_evaluation_metrics (
    metric_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    population_id UUID REFERENCES system_evaluation_populations(population_id),
    metric_name VARCHAR(100),
    metric_category VARCHAR(100),  -- completion, success, failure, repair, attempt, verification, efficiency, etc.
    value NUMERIC,
    sample_count BIGINT,
    independent_entities BIGINT,  -- distinct tasks, nodes, etc.
    data_sources JSONB,  -- which tables/queries produced this metric
    definition JSONB,  -- how was this metric calculated
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_metrics_evaluation ON system_evaluation_metrics(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_eval_metrics_population ON system_evaluation_metrics(population_id);

-- Comparisons: Track comparative evaluations
CREATE TABLE IF NOT EXISTS system_evaluation_comparisons (
    comparison_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    comparison_type VARCHAR(100),  -- baseline_vs_current, before_after, control_treatment, config_a_vs_b, etc.
    population_a_id UUID REFERENCES system_evaluation_populations(population_id),
    population_b_id UUID REFERENCES system_evaluation_populations(population_id),
    metric_name VARCHAR(100),
    value_a NUMERIC,
    value_b NUMERIC,
    difference NUMERIC,
    direction VARCHAR(20),  -- improved, degraded, no_material_change
    evidence_sufficiency VARCHAR(50),
    conclusion VARCHAR(100),
    confounders TEXT,
    comparability_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_comparisons_evaluation ON system_evaluation_comparisons(evaluation_id);

-- Findings: Structured evaluation findings
CREATE TABLE IF NOT EXISTS system_evaluation_findings (
    finding_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    finding_type VARCHAR(100),  -- improvement, regression, mixed, bottleneck, gap, insufficient, possible_issue, etc.
    scope VARCHAR(100),  -- orchestration, experimentation, validation, node_evolution, self_org, governance, etc.
    population_id UUID REFERENCES system_evaluation_populations(population_id),
    metric_references JSONB,
    severity VARCHAR(50),
    direction VARCHAR(20),  -- improved, degraded, mixed, neutral
    evidence_sufficiency VARCHAR(50),
    confidence_level VARCHAR(50),  -- supported, likely, possible, speculative
    explanation TEXT,
    limitations TEXT,
    supporting_metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_findings_evaluation ON system_evaluation_findings(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_eval_findings_type ON system_evaluation_findings(finding_type);

-- Regressions: Explicit regression tracking
CREATE TABLE IF NOT EXISTS system_regressions (
    regression_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    regression_type VARCHAR(100),  -- performance, reliability, verification, repair_burden, etc.
    affected_scope VARCHAR(100),
    population_id UUID REFERENCES system_evaluation_populations(population_id),
    baseline_value NUMERIC,
    current_value NUMERIC,
    degradation_magnitude NUMERIC,
    degradation_direction VARCHAR(20),
    affected_entity_count BIGINT,
    evidence_sufficiency VARCHAR(50),
    potential_causes JSONB,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_regressions_evaluation ON system_regressions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_regressions_type ON system_regressions(regression_type);

-- Change impact: Link evaluations to system changes
CREATE TABLE IF NOT EXISTS system_change_evaluations (
    change_eval_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    change_type VARCHAR(100),  -- strategy_promotion, knowledge_promotion, config_change, policy_change, etc.
    change_id VARCHAR(255),
    change_version VARCHAR(50),
    pre_change_baseline_id UUID REFERENCES system_evaluation_baselines(baseline_id),
    post_change_population_id UUID REFERENCES system_evaluation_populations(population_id),
    observed_outcomes JSONB,
    metric_comparisons JSONB,
    sufficiency_assessment VARCHAR(50),
    conclusion VARCHAR(100),
    causation_claim VARCHAR(50),  -- observed_association, experimental_evidence, validated_evidence, no_causal_claim
    limitations TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_change_eval_evaluation ON system_change_evaluations(evaluation_id);

-- Trends: System-level trends across evaluations
CREATE TABLE IF NOT EXISTS system_trends (
    trend_id UUID PRIMARY KEY,
    trend_name VARCHAR(255),
    metric_name VARCHAR(100),
    evaluation_window_days INT,  -- e.g., 30-day trend
    current_evaluation_id UUID REFERENCES system_evaluation_runs(evaluation_id),
    prior_evaluation_id UUID REFERENCES system_evaluation_runs(evaluation_id),
    direction VARCHAR(100),  -- improving, stable, degrading, mixed, insufficient_evidence
    underlying_observations JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trends_metric ON system_trends(metric_name);
CREATE INDEX IF NOT EXISTS idx_trends_current_eval ON system_trends(current_evaluation_id);

-- Subsystem evaluations: Evidence-based subsystem health
CREATE TABLE IF NOT EXISTS system_subsystem_evaluations (
    subsys_eval_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    subsystem_name VARCHAR(100),  -- learning, orchestration, experimentation, validation, evolution, self_org, governance
    status VARCHAR(50),  -- operational, degraded, failed
    operational_evidence JSONB,  -- metrics from actual subsystem operations
    effectiveness_evidence JSONB,  -- outcomes evidence
    failure_attribution JSONB,  -- where failures occurred
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_subsys_eval_evaluation ON system_subsystem_evaluations(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_subsys_eval_subsystem ON system_subsystem_evaluations(subsystem_name);

-- Governance effectiveness: Track governance performance
CREATE TABLE IF NOT EXISTS system_governance_effectiveness (
    gov_eval_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    protected_actions_evaluated BIGINT,
    allow_decisions BIGINT,
    allow_with_constraints BIGINT,
    require_approval_decisions BIGINT,
    deny_decisions BIGINT,
    approvals_requested BIGINT,
    approvals_granted BIGINT,
    approvals_denied BIGINT,
    approvals_revoked BIGINT,
    blocked_unauthorised_attempts BIGINT,
    fail_closed_events BIGINT,
    authorised_protected_executions BIGINT,
    governance_bypass_attempts BIGINT,
    tradeoff_assessment TEXT,  -- balance between blocking and allowing
    effectiveness_conclusion VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_gov_eval_evaluation ON system_governance_effectiveness(evaluation_id);

-- Failure attribution: Track failure context and causes
CREATE TABLE IF NOT EXISTS system_failure_attribution (
    attribution_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    failure_context VARCHAR(100),  -- task, strategy, node, orchestration, verification, repair, structure, governance, etc.
    population_id UUID REFERENCES system_evaluation_populations(population_id),
    failure_count BIGINT,
    failure_rate NUMERIC,
    primary_contributor VARCHAR(100),  -- observed vs suspected vs validated
    contributing_factors JSONB,
    evidence_class VARCHAR(50),  -- observed, suspected, experimentally_supported, validated
    limitations TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_failure_attr_evaluation ON system_failure_attribution(evaluation_id);

-- Recommended next actions (non-executing): Advisory classifications only
CREATE TABLE IF NOT EXISTS system_evaluation_recommendations (
    rec_id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES system_evaluation_runs(evaluation_id),
    finding_id UUID REFERENCES system_evaluation_findings(finding_id),
    recommendation_class VARCHAR(100),  -- retain, monitor, investigate, collect_more_evidence, run_experiment, revalidate, consider_restriction, no_action
    rationale TEXT,
    suggested_investigation TEXT,
    evidence_basis JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (evaluation_id) REFERENCES system_evaluation_runs(evaluation_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_evaluation ON system_evaluation_recommendations(evaluation_id);

-- Evaluation rules: Versioned evaluation configuration
CREATE TABLE IF NOT EXISTS system_evaluation_rule_versions (
    rule_version INT PRIMARY KEY,
    minimum_sample_count INT,
    minimum_independent_entities INT,
    regression_threshold_percent NUMERIC,
    material_change_threshold_percent NUMERIC,
    trend_window_days INT,
    missing_data_handling VARCHAR(50),  -- exclude, impute_last_known, flag_insufficient
    contradiction_handling VARCHAR(50),  -- investigate, flag, downgrade_confidence
    evidence_sufficiency_rules JSONB,
    comparison_requirements JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    description TEXT
);

-- Events/observability integration
-- Re-use existing events table or ensure compatibility
CREATE TABLE IF NOT EXISTS system_evaluation_events (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(100),  -- system_evaluation_created, system_evaluation_completed, system_regression_detected, etc.
    evaluation_id UUID REFERENCES system_evaluation_runs(evaluation_id),
    severity VARCHAR(50),
    description TEXT,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_events_evaluation ON system_evaluation_events(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_eval_events_type ON system_evaluation_events(event_type);

-- Insert default evaluation rules (version 1)
INSERT INTO system_evaluation_rule_versions (
    rule_version,
    minimum_sample_count,
    minimum_independent_entities,
    regression_threshold_percent,
    material_change_threshold_percent,
    trend_window_days,
    missing_data_handling,
    contradiction_handling,
    evidence_sufficiency_rules,
    comparison_requirements,
    description
) VALUES (
    1,
    5,
    3,
    10.0,
    5.0,
    30,
    'exclude',
    'investigate',
    '{"sufficiency_classes": ["insufficient", "limited", "adequate", "strong"]}',
    '{"same_population": true, "time_ordering": true, "baseline_frozen": true}',
    'Initial evaluation rules: conservative thresholds, require multiple independent observations'
) ON CONFLICT DO NOTHING;
