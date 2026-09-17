-- SECTION 23: FULL EVOLUTIONARY LOOP
-- Migration for integrated end-to-end evolutionary cycles
-- Joins Sections 2-22 into controlled adaptive evolution

BEGIN;

-- Evolutionary cycle core tables
CREATE TABLE IF NOT EXISTS evolution_cycles (
    cycle_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    trigger_source character varying(50) NOT NULL,
    trigger_reference uuid,
    objective text,
    work_population jsonb,
    scope character varying(255),
    status character varying(50) DEFAULT 'created' NOT NULL,
    current_stage character varying(100),
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    data_cutoff timestamp with time zone,
    rule_version character varying(50),
    config_version character varying(50),
    governance_references jsonb,
    result jsonb,
    termination_reason character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    created_by uuid,
    CONSTRAINT valid_status CHECK (status IN ('created', 'running', 'waiting_for_evidence', 'waiting_for_approval', 'experimenting', 'validating', 'evaluating', 'completed', 'no_change', 'restricted', 'failed', 'terminated')),
    CONSTRAINT valid_trigger CHECK (trigger_source IN ('new_work_demand', 'repeated_failure', 'repair_burden', 'strategy_underperformance', 'orchestration_uncertainty', 'experiment_opportunity', 'validation_result', 'node_capability_gap', 'organisational_bottleneck', 'system_regression', 'system_improvement', 'human_request'))
);

CREATE TABLE IF NOT EXISTS evolution_cycle_stages (
    stage_record_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    stage character varying(100) NOT NULL,
    input_references jsonb,
    output_references jsonb,
    decision_references jsonb,
    started_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    status character varying(50) NOT NULL,
    reason text,
    governance_decision jsonb,
    errors jsonb,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT valid_stage_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    CONSTRAINT valid_stage_type CHECK (stage IN ('retrieval', 'context', 'strategy_selection', 'adaptive_orchestration', 'node_selection', 'org_structure', 'execution', 'attempts', 'verification', 'failures_repairs', 'outcome', 'learning_feedback', 'knowledge_evolution', 'strategy_evolution', 'uncertainty_detection', 'experimentation', 'validation', 'promotion', 'node_evolution', 'org_evolution', 'system_evaluation', 'regression_response', 'governance_decision'))
);

CREATE TABLE IF NOT EXISTS evolution_cycle_triggers (
    trigger_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    source character varying(50) NOT NULL,
    source_reference uuid,
    evidence jsonb,
    confidence double precision,
    detected_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_cycle_decisions (
    decision_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    stage character varying(100) NOT NULL,
    what_was_observed text,
    evidence_considered jsonb,
    change_proposed character varying(255),
    change_rationale text,
    controlled_subsystem character varying(100),
    governance_result character varying(50),
    validation_result character varying(50),
    system_evaluation_result character varying(50),
    future_applicability text,
    termination_reason character varying(255),
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_cycle_evidence_links (
    link_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    stage character varying(100),
    evidence_type character varying(100),
    evidence_id uuid,
    evidence_table character varying(100),
    sequence_order integer,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_cycle_summary (
    summary_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL UNIQUE REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    trigger_summary text,
    task_references jsonb,
    retrieved_evidence_summary jsonb,
    strategy_selected character varying(255),
    node_selected character varying(255),
    structure_used character varying(255),
    execution_attempts integer,
    repairs_performed integer,
    final_outcome character varying(50),
    learning_generated boolean,
    experiment_run boolean,
    validation_performed boolean,
    node_evolution_applied boolean,
    org_evolution_applied boolean,
    regression_detected boolean,
    system_eval_finding character varying(255),
    future_adaptation_enabled boolean,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_cycle_idempotency (
    idempotency_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL UNIQUE REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    request_idempotency_key character varying(255),
    equivalent_cycle_ids uuid[],
    conflict_detected boolean DEFAULT false,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_management_plane_blocks (
    block_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    target_keyword character varying(100) NOT NULL,
    target_description text,
    proposed_action text,
    reasoning text,
    rejected_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    UNIQUE (cycle_id, target_keyword)
);

CREATE TABLE IF NOT EXISTS evolution_churn_prevention (
    prevention_id uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
    cycle_id uuid NOT NULL REFERENCES evolution_cycles(cycle_id) ON DELETE CASCADE,
    previous_decision_cycle uuid REFERENCES evolution_cycles(cycle_id),
    previous_change_proposed character varying(255),
    new_change_proposed character varying(255),
    evidence_delta jsonb,
    new_evidence_justifies_change boolean,
    churn_risk_level character varying(50),
    created_at timestamp with time zone DEFAULT now()
);

-- Create indices for performance
CREATE INDEX IF NOT EXISTS idx_evolution_cycles_status ON evolution_cycles(status);
CREATE INDEX IF NOT EXISTS idx_evolution_cycles_trigger ON evolution_cycles(trigger_source);
CREATE INDEX IF NOT EXISTS idx_evolution_cycles_created ON evolution_cycles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_stages_cycle ON evolution_cycle_stages(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_stages_stage ON evolution_cycle_stages(stage);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_triggers_cycle ON evolution_cycle_triggers(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_decisions_cycle ON evolution_cycle_decisions(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_decisions_stage ON evolution_cycle_decisions(stage);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_evidence_cycle ON evolution_cycle_evidence_links(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_cycle_summary_cycle ON evolution_cycle_summary(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_churn_prevention_cycle ON evolution_churn_prevention(cycle_id);
CREATE INDEX IF NOT EXISTS idx_evolution_management_plane_cycle ON evolution_management_plane_blocks(cycle_id);

COMMIT;
