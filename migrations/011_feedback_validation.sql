-- Section 11: Feedback & Validation Layer
-- Closes the learning loop: execution outcome → evaluation → evidence → confidence update → validation state

-- Immutable feedback records linking attempts to outcomes to applied learning
CREATE TABLE feedback_records (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    outcome_id UUID REFERENCES task_outcomes(outcome_id),
    applied_learning_id UUID REFERENCES applied_learning(applied_id),
    learning_type TEXT NOT NULL, -- outcome, pattern, insight, artifact, graph_entity
    learning_id UUID NOT NULL,
    
    -- Execution snapshot
    execution_guidance_snapshot JSONB,
    execution_guidance_id UUID REFERENCES execution_guidance(guidance_id),
    
    -- Result & quality
    result JSONB,
    quality_score NUMERIC(3,2) CHECK (quality_score >= 0 AND quality_score <= 1),
    execution_time_seconds INTEGER,
    outcome_status TEXT NOT NULL, -- success, partial, failure
    
    -- Effect classification
    effect_classification TEXT NOT NULL CHECK (effect_classification IN ('supportive', 'contradictory', 'neutral', 'insufficient_evidence')),
    effect_reasoning JSONB, -- Explanation of classification
    
    -- Baseline comparison
    baseline_type TEXT, -- none, same_task_type, same_node, historical_avg
    baseline_quality NUMERIC(3,2),
    baseline_count INTEGER, -- How many prior attempts for baseline
    quality_delta NUMERIC(4,3), -- quality_score - baseline_quality
    
    -- Evidence metadata
    evidence_strength NUMERIC(3,2), -- 0-1, confidence in the comparison
    comparable BOOLEAN DEFAULT TRUE, -- Whether baseline is valid
    
    -- Attribution clarity
    learning_applied_only BOOLEAN DEFAULT FALSE, -- Was this the only learning applied?
    conflicting_learning_count INTEGER DEFAULT 0, -- Other learning applied simultaneously
    external_variables JSONB, -- Known confounding factors
    
    -- Causality note
    attribution_confidence TEXT CHECK (attribution_confidence IN ('associated', 'likely', 'unclear', 'conflicting')),
    causality_note TEXT, -- Human-readable note about causal claim
    
    -- Immutability & audit
    feedback_version INTEGER DEFAULT 1, -- For rare corrections/updates
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT DEFAULT 'system', -- Which node/component created
    metadata JSONB,
    
    -- Deduplication
    feedback_hash VARCHAR(64) UNIQUE, -- SHA256(attempt_id || applied_learning_id || outcome_id)
    
    CONSTRAINT feedback_references_valid CHECK (
        (learning_type IN ('outcome', 'pattern', 'insight', 'artifact', 'graph_entity'))
    )
);

CREATE INDEX idx_feedback_attempt ON feedback_records(attempt_id);
CREATE INDEX idx_feedback_learning ON feedback_records(learning_id, learning_type);
CREATE INDEX idx_feedback_node ON feedback_records(node_id);
CREATE INDEX idx_feedback_classification ON feedback_records(effect_classification);
CREATE INDEX idx_feedback_task ON feedback_records(task_id);
CREATE INDEX idx_feedback_created ON feedback_records(created_at DESC);
CREATE INDEX idx_feedback_hash ON feedback_records(feedback_hash);

-- Evidence accumulation per learning item
-- Aggregates across all times this learning has been applied
CREATE TABLE evidence_accumulation (
    accumulation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_id UUID NOT NULL,
    learning_type TEXT NOT NULL, -- outcome, pattern, insight, artifact, graph_entity
    
    -- Aggregate counts
    times_applied INTEGER DEFAULT 0,
    supportive_count INTEGER DEFAULT 0,
    contradictory_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    insufficient_evidence_count INTEGER DEFAULT 0,
    
    -- Ratios (cached for performance)
    supportive_ratio NUMERIC(3,2) DEFAULT 0, -- supportive_count / times_applied
    contradictory_ratio NUMERIC(3,2) DEFAULT 0,
    
    -- Quality metrics
    avg_quality_when_applied NUMERIC(3,2),
    avg_quality_delta NUMERIC(4,3), -- Average improvement/degradation
    quality_variance NUMERIC(5,3),
    
    -- Task type coverage
    task_types JSONB, -- {"task_type": count, ...}
    node_count INTEGER, -- How many different nodes applied this
    
    -- Time tracking
    first_applied TIMESTAMPTZ,
    last_applied TIMESTAMPTZ,
    last_evaluated TIMESTAMPTZ,
    
    -- Validation-related
    current_validation_state TEXT CHECK (current_validation_state IN ('candidate', 'emerging', 'validated', 'disputed', 'rejected')),
    validation_changed_at TIMESTAMPTZ,
    
    -- For Section 9 integration
    confidence_score NUMERIC(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    evidence_count INTEGER DEFAULT 0, -- Total feedback records
    
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(learning_id, learning_type)
);

CREATE INDEX idx_evidence_learning ON evidence_accumulation(learning_id, learning_type);
CREATE INDEX idx_evidence_validation ON evidence_accumulation(current_validation_state);
CREATE INDEX idx_evidence_confidence ON evidence_accumulation(confidence_score DESC);
CREATE INDEX idx_evidence_task_types ON evidence_accumulation USING GIN(task_types);

-- Confidence adjustment history
-- Track when and why confidence changes
CREATE TABLE confidence_adjustments (
    adjustment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_id UUID NOT NULL,
    learning_type TEXT NOT NULL,
    
    -- Previous & new
    previous_confidence NUMERIC(3,2),
    new_confidence NUMERIC(3,2),
    confidence_change NUMERIC(4,3),
    
    -- What caused it
    trigger_type TEXT CHECK (trigger_type IN ('feedback', 'decay', 'manual', 'override', 'reset')),
    feedback_id UUID REFERENCES feedback_records(feedback_id),
    trigger_reason TEXT,
    
    -- Evidence state at time of adjustment
    supportive_count_at_adjustment INTEGER,
    contradictory_count_at_adjustment INTEGER,
    evidence_count_at_adjustment INTEGER,
    
    -- Adjustment logic
    adjustment_rule TEXT, -- Documented rule that was applied
    adjustment_magnitude NUMERIC(4,3), -- |previous - new|
    
    adjusted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    adjusted_by TEXT DEFAULT 'system',
    metadata JSONB,
    
    FOREIGN KEY (learning_id) REFERENCES evidence_accumulation(learning_id)
);

CREATE INDEX idx_adjustments_learning ON confidence_adjustments(learning_id);
CREATE INDEX idx_adjustments_trigger ON confidence_adjustments(trigger_type);
CREATE INDEX idx_adjustments_time ON confidence_adjustments(adjusted_at DESC);

-- Validation state transitions
-- Track when and why learning moves between candidate/emerging/validated/disputed/rejected
CREATE TABLE validation_transitions (
    transition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_id UUID NOT NULL,
    learning_type TEXT NOT NULL,
    
    -- State change
    from_state TEXT CHECK (from_state IN ('candidate', 'emerging', 'validated', 'disputed', 'rejected', NULL)),
    to_state TEXT CHECK (to_state IN ('candidate', 'emerging', 'validated', 'disputed', 'rejected')),
    
    -- What triggered it
    trigger_type TEXT CHECK (trigger_type IN ('evidence_threshold', 'feedback', 'manual', 'override')),
    trigger_reason TEXT,
    triggering_feedback_id UUID REFERENCES feedback_records(feedback_id),
    
    -- Evidence state at transition
    evidence_state JSONB, -- {supportive_count, contradictory_count, ratio, ...}
    thresholds_checked JSONB, -- Which thresholds were evaluated
    
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    transitioned_by TEXT DEFAULT 'system',
    metadata JSONB,
    
    FOREIGN KEY (learning_id) REFERENCES evidence_accumulation(learning_id)
);

CREATE INDEX idx_transitions_learning ON validation_transitions(learning_id);
CREATE INDEX idx_transitions_state ON validation_transitions(from_state, to_state);
CREATE INDEX idx_transitions_time ON validation_transitions(transitioned_at DESC);

-- Effect classifications (read-only reference)
-- Defines the rules for supportive/contradictory/neutral/insufficient_evidence
CREATE TABLE effect_classification_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    classification TEXT NOT NULL CHECK (classification IN ('supportive', 'contradictory', 'neutral', 'insufficient_evidence')),
    
    -- Rule definition
    rule_description TEXT,
    quality_improvement_threshold NUMERIC(4,3), -- e.g., 0.05 = 5%
    quality_degradation_threshold NUMERIC(4,3), -- e.g., 0.05 = 5%
    
    -- Applicability
    requires_baseline BOOLEAN DEFAULT TRUE,
    min_baseline_evidence INTEGER DEFAULT 3,
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE
);

INSERT INTO effect_classification_rules (classification, rule_description, quality_improvement_threshold, quality_degradation_threshold, requires_baseline, min_baseline_evidence, active)
VALUES
    ('supportive', 'Outcome quality > baseline + threshold', 0.05, NULL, TRUE, 3, TRUE),
    ('contradictory', 'Outcome quality < baseline - threshold', NULL, 0.05, TRUE, 3, TRUE),
    ('neutral', 'Outcome within ±threshold of baseline', 0.05, 0.05, TRUE, 3, TRUE),
    ('insufficient_evidence', 'No valid baseline for comparison', NULL, NULL, FALSE, 0, TRUE)
ON CONFLICT DO NOTHING;

-- Baseline comparisons (for audit/analysis)
-- Historical baselines used for outcome comparisons
CREATE TABLE baseline_comparisons (
    comparison_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID NOT NULL REFERENCES feedback_records(feedback_id),
    
    -- What was compared
    task_id UUID REFERENCES tasks(task_id),
    task_type TEXT,
    learning_item_id UUID,
    
    -- Baseline source
    baseline_type TEXT NOT NULL CHECK (baseline_type IN ('same_task_type', 'same_node', 'historical_avg', 'peer_avg', 'none')),
    baseline_description TEXT,
    
    -- Baseline metrics
    baseline_attempt_ids UUID[] DEFAULT ARRAY[]::UUID[], -- What attempts formed the baseline
    baseline_count INTEGER,
    baseline_quality NUMERIC(3,2),
    baseline_success_rate NUMERIC(3,2),
    baseline_avg_time_seconds INTEGER,
    
    -- Comparison result
    quality_delta NUMERIC(4,3),
    time_delta INTEGER,
    success_improved BOOLEAN,
    
    -- Confidence in comparison
    comparable BOOLEAN DEFAULT TRUE,
    comparability_notes TEXT,
    confounding_factors JSONB,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_baseline_feedback ON baseline_comparisons(feedback_id);
CREATE INDEX idx_baseline_type ON baseline_comparisons(baseline_type);
CREATE INDEX idx_baseline_task ON baseline_comparisons(task_type);

-- Negative learning feedback
-- Special handling for warnings/avoidance guidance
CREATE TABLE negative_learning_feedback (
    nlf_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID NOT NULL REFERENCES feedback_records(feedback_id),
    warning_learning_id UUID NOT NULL,
    
    -- What was warned against
    warning_description TEXT,
    warning_type TEXT, -- avoidance, constraint, weakness, etc.
    
    -- Was the warning relevant?
    warning_applied BOOLEAN, -- Was the node actually following the warning?
    warning_relevant BOOLEAN, -- Could this outcome have been affected by the warning?
    
    -- Evidence for/against the warning
    support_type TEXT CHECK (support_type IN ('warning_followed_good_outcome', 'warning_ignored_bad_outcome', 'warning_ignored_good_outcome', 'warning_followed_bad_outcome', 'inconclusive')),
    support_reasoning TEXT,
    support_strength NUMERIC(3,2),
    
    -- Outcome vs what would have been without warning
    counterfactual_note TEXT, -- Can't know without actual experiment
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nlf_feedback ON negative_learning_feedback(feedback_id);
CREATE INDEX idx_nlf_warning ON negative_learning_feedback(warning_learning_id);
CREATE INDEX idx_nlf_support ON negative_learning_feedback(support_type);

-- Feedback processing log
-- Track processing status for idempotency and debugging
CREATE TABLE feedback_processing_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    outcome_id UUID REFERENCES task_outcomes(outcome_id),
    
    -- Processing status
    processing_status TEXT NOT NULL CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed', 'duplicate')),
    processing_error TEXT,
    
    -- If duplicate
    original_feedback_id UUID REFERENCES feedback_records(feedback_id),
    duplicate_detected BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    processed_at TIMESTAMPTZ,
    processing_duration_ms INTEGER,
    feedback_records_created INTEGER DEFAULT 0,
    evidence_updated INTEGER DEFAULT 0,
    confidence_adjustments_made INTEGER DEFAULT 0,
    state_transitions_made INTEGER DEFAULT 0,
    
    -- Trace for audit
    processing_trace JSONB,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fplog_attempt ON feedback_processing_log(attempt_id);
CREATE INDEX idx_fplog_status ON feedback_processing_log(processing_status);
CREATE INDEX idx_fplog_time ON feedback_processing_log(created_at DESC);
CREATE UNIQUE INDEX idx_fplog_outcome ON feedback_processing_log(attempt_id, outcome_id) WHERE outcome_id IS NOT NULL;

-- Validation state constants (for reference/documentation)
CREATE TABLE validation_state_reference (
    state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_name TEXT NOT NULL UNIQUE CHECK (state_name IN ('candidate', 'emerging', 'validated', 'disputed', 'rejected')),
    
    -- State characteristics
    description TEXT,
    characteristics JSONB, -- {min_evidence, supportive_ratio, ...}
    
    -- Transitions
    can_transition_to TEXT[] DEFAULT ARRAY[]::TEXT[], -- Which states this can transition to
    
    -- Usage in retrieval/application
    suitable_for_positive_guidance BOOLEAN,
    suitable_for_warnings BOOLEAN,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO validation_state_reference (state_name, description, characteristics, can_transition_to, suitable_for_positive_guidance, suitable_for_warnings)
VALUES
    ('candidate', 'Initial state, minimal evidence', '{"min_evidence": 0, "supportive_ratio": null}', ARRAY['emerging', 'validated', 'rejected'], FALSE, FALSE),
    ('emerging', 'Growing evidence, trend visible', '{"min_evidence": 3, "supportive_ratio": 0.5}', ARRAY['validated', 'disputed', 'candidate', 'rejected'], TRUE, TRUE),
    ('validated', 'Strong evidence, consistently helpful', '{"min_evidence": 5, "supportive_ratio": 0.7}', ARRAY['disputed', 'emerging', 'rejected'], TRUE, TRUE),
    ('disputed', 'Mixed evidence, conflicting outcomes', '{"min_evidence": 5, "contradictory_ratio": 0.3}', ARRAY['validated', 'rejected', 'candidate'], TRUE, TRUE),
    ('rejected', 'Overwhelmingly contradicted', '{"min_evidence": 5, "contradictory_ratio": 0.8}', ARRAY['disputed', 'candidate'], FALSE, FALSE)
ON CONFLICT DO NOTHING;

-- Feedback configuration
-- Tunable parameters for confidence/state transitions
CREATE TABLE feedback_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_name TEXT UNIQUE NOT NULL,
    
    -- Confidence adjustments
    confidence_increase_per_supportive NUMERIC(3,2) DEFAULT 0.10,
    confidence_decrease_per_contradictory NUMERIC(3,2) DEFAULT 0.10,
    min_evidence_for_confidence_move INTEGER DEFAULT 3, -- Need this many before confidence moves
    confidence_min NUMERIC(3,2) DEFAULT 0.05,
    confidence_max NUMERIC(3,2) DEFAULT 0.95,
    
    -- State transitions: candidate → emerging
    emerging_threshold_min_evidence INTEGER DEFAULT 3,
    emerging_threshold_supportive_ratio NUMERIC(3,2) DEFAULT 0.5,
    
    -- State transitions: emerging → validated
    validated_threshold_min_evidence INTEGER DEFAULT 5,
    validated_threshold_supportive_ratio NUMERIC(3,2) DEFAULT 0.70,
    
    -- State transitions: disputed
    disputed_threshold_min_evidence INTEGER DEFAULT 5,
    disputed_threshold_contradictory_ratio NUMERIC(3,2) DEFAULT 0.30,
    
    -- State transitions: rejected
    rejected_threshold_min_evidence INTEGER DEFAULT 5,
    rejected_threshold_contradictory_ratio NUMERIC(3,2) DEFAULT 0.80,
    
    -- Effect classification
    supportive_quality_delta_threshold NUMERIC(4,3) DEFAULT 0.05, -- 5% improvement
    contradictory_quality_delta_threshold NUMERIC(4,3) DEFAULT 0.05, -- 5% degradation
    
    -- Baseline requirements
    min_baseline_attempts INTEGER DEFAULT 3,
    baseline_task_type_match BOOLEAN DEFAULT TRUE,
    baseline_node_match_preferred BOOLEAN DEFAULT FALSE,
    
    -- Automatic decay (future use)
    enable_confidence_decay BOOLEAN DEFAULT FALSE,
    decay_rate_per_day NUMERIC(4,3) DEFAULT 0.01,
    
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO feedback_config (config_name, active)
VALUES ('default', TRUE)
ON CONFLICT DO NOTHING;

-- Helper function: record event for feedback transitions
-- (Reuses existing record_event function from Section 3)

COMMIT;
