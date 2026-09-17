-- Section 12: Cross-Node Learning Distribution
-- Enables validated learning from one node to be safely shared with other nodes
-- while preserving provenance, scope, and conflict information

BEGIN;

-- Promotion eligibility rules (deterministic criteria for organisational learning)
CREATE TABLE IF NOT EXISTS promotion_eligibility_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL UNIQUE,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('confidence_threshold', 'evidence_count', 'validation_state', 'task_type_required', 'contradiction_check')),
    parameter JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Organisational learning: learning eligible for cross-node sharing
CREATE TABLE IF NOT EXISTS organisational_learning (
    org_learning_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_learning_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('outcome', 'pattern', 'insight', 'artifact')),
    source_node_id UUID NOT NULL,
    source_task_type TEXT NOT NULL,
    task_type TEXT NOT NULL,  -- applicability scope
    content JSONB NOT NULL,
    promotion_reason TEXT,
    promoted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promotion_confidence NUMERIC(5,4) NOT NULL DEFAULT 0.8,
    current_state TEXT NOT NULL DEFAULT 'organisational' CHECK (current_state IN ('organisational', 'disputed', 'restricted', 'retired')),
    access_scope JSONB,  -- future: node restrictions, task type constraints
    evidence_count INT DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (source_node_id) REFERENCES nodes(node_id)
);

-- Learning promotion history: audit trail of state transitions
CREATE TABLE IF NOT EXISTS learning_promotion_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_learning_id UUID NOT NULL,
    transition_from TEXT NOT NULL,
    transition_to TEXT NOT NULL,
    reason TEXT,
    triggered_by TEXT DEFAULT 'automated',  -- 'automated' or 'manual'
    trigger_evidence JSONB,  -- supporting data (contradictions, etc.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_learning_id) REFERENCES organisational_learning(org_learning_id) ON DELETE CASCADE
);

-- Cross-node distribution record: which nodes accessed which learning
CREATE TABLE IF NOT EXISTS cross_node_distribution (
    distribution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_learning_id UUID NOT NULL,
    source_node_id UUID NOT NULL,
    target_node_id UUID NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    context_package_id UUID,  -- from Section 9 retrieval
    retrieval_trace_id UUID,  -- from Section 9
    applied_attempt_id UUID,  -- if applied to attempt
    application_timestamp TIMESTAMPTZ,
    distribution_status TEXT NOT NULL DEFAULT 'available' CHECK (distribution_status IN ('available', 'applied', 'used_in_outcome')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_learning_id) REFERENCES organisational_learning(org_learning_id) ON DELETE CASCADE,
    FOREIGN KEY (source_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (target_node_id) REFERENCES nodes(node_id)
);

-- Evidence linking: how other nodes' outcomes support/contradict organisational learning
CREATE TABLE IF NOT EXISTS cross_node_evidence_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_learning_id UUID NOT NULL,
    outcome_id UUID NOT NULL,
    source_node_id UUID NOT NULL,  -- original node that produced the learning
    consuming_node_id UUID NOT NULL,  -- node that used it and produced this outcome
    agreement_type TEXT NOT NULL CHECK (agreement_type IN ('supportive', 'contradictory', 'neutral')),
    agreement_confidence NUMERIC(5,4) NOT NULL,
    distribution_id UUID,
    evidence_summary JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_learning_id) REFERENCES organisational_learning(org_learning_id) ON DELETE CASCADE,
    FOREIGN KEY (outcome_id) REFERENCES task_outcomes(outcome_id),
    FOREIGN KEY (source_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (consuming_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (distribution_id) REFERENCES cross_node_distribution(distribution_id)
);

-- Applied organisational learning: records when cross-node learning is applied to an attempt
CREATE TABLE IF NOT EXISTS applied_organisational_learning (
    applied_org_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_learning_id UUID NOT NULL,
    attempt_id UUID NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applicability_score NUMERIC(5,4) NOT NULL,
    is_contradicted_locally BOOLEAN DEFAULT FALSE,
    local_contradiction_confidence NUMERIC(5,4),
    applied_in_context JSONB,  -- context where applied
    FOREIGN KEY (org_learning_id) REFERENCES organisational_learning(org_learning_id) ON DELETE CASCADE,
    FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_org_learning_source_node ON organisational_learning(source_node_id);
CREATE INDEX IF NOT EXISTS idx_org_learning_task_type ON organisational_learning(task_type);
CREATE INDEX IF NOT EXISTS idx_org_learning_state ON organisational_learning(current_state);
CREATE INDEX IF NOT EXISTS idx_org_learning_promoted_at ON organisational_learning(promoted_at DESC);

CREATE INDEX IF NOT EXISTS idx_promotion_history_org_learning ON learning_promotion_history(org_learning_id);
CREATE INDEX IF NOT EXISTS idx_promotion_history_timestamp ON learning_promotion_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cross_dist_org_learning ON cross_node_distribution(org_learning_id);
CREATE INDEX IF NOT EXISTS idx_cross_dist_target_node ON cross_node_distribution(target_node_id);
CREATE INDEX IF NOT EXISTS idx_cross_dist_source_node ON cross_node_distribution(source_node_id);
CREATE INDEX IF NOT EXISTS idx_cross_dist_retrieved ON cross_node_distribution(retrieved_at DESC);

CREATE INDEX IF NOT EXISTS idx_cross_evidence_org_learning ON cross_node_evidence_links(org_learning_id);
CREATE INDEX IF NOT EXISTS idx_cross_evidence_agreement ON cross_node_evidence_links(agreement_type);
CREATE INDEX IF NOT EXISTS idx_cross_evidence_nodes ON cross_node_evidence_links(source_node_id, consuming_node_id);

CREATE INDEX IF NOT EXISTS idx_applied_org_org_learning ON applied_organisational_learning(org_learning_id);
CREATE INDEX IF NOT EXISTS idx_applied_org_attempt ON applied_organisational_learning(attempt_id);

-- Default promotion eligibility rules
INSERT INTO promotion_eligibility_rules (rule_name, rule_type, parameter, description)
VALUES
  ('min_confidence_threshold', 'confidence_threshold', '{"threshold": 0.75}', 'Learning must have ≥75% confidence'),
  ('min_evidence_count', 'evidence_count', '{"count": 2}', 'Learning must have ≥2 pieces of evidence'),
  ('validation_state_required', 'validation_state', '{"states": ["confirmed", "recommended"]}', 'Validation state must be confirmed or recommended'),
  ('task_type_required', 'task_type_required', '{"required": true}', 'Learning must specify applicable task type'),
  ('no_high_confidence_contradiction', 'contradiction_check', '{"allow_contradictions": false, "threshold": 0.7}', 'Learning with contradictions >70% confidence ineligible')
ON CONFLICT (rule_name) DO NOTHING;

COMMIT;
