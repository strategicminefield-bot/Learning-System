-- Section 13: Knowledge Evolution
-- Allows organisational knowledge to evolve over time based on accumulated evidence
-- while preserving provenance, history, contradictions and reversibility

-- Knowledge Entity: Persistent identity for a knowledge concept
CREATE TABLE IF NOT EXISTS knowledge_entities (
    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,  -- knowledge_item, organisational_learning, artifact, pattern, insight
    task_type TEXT NOT NULL,
    original_source_id UUID,  -- Original source (org_learning_id, artifact_id, etc.)
    created_at TIMESTAMPTZ DEFAULT now(),
    first_evidence_at TIMESTAMPTZ,
    last_evidence_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entities_task_type ON knowledge_entities(task_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_entity_type ON knowledge_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_entities_source ON knowledge_entities(original_source_id);

-- Knowledge Versions: Each revision preserves parent/predecessor
CREATE TABLE IF NOT EXISTS knowledge_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_number INT NOT NULL,  -- 1, 2, 3...
    parent_version_id UUID,  -- Predecessor version
    content JSONB NOT NULL,
    applicability JSONB,  -- Scope/constraints
    validation_state TEXT,  -- confirmed, recommended, uncertain, invalidated
    confidence NUMERIC(5,4),  -- 0-1 confidence score
    creation_reason TEXT,  -- why this version was created
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by_node_id UUID,  -- Which node created this version
    created_by_rule TEXT,  -- Which evolution rule triggered this version
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    UNIQUE(entity_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_versions_entity ON knowledge_versions(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_parent ON knowledge_versions(parent_version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_state ON knowledge_versions(validation_state);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_confidence ON knowledge_versions(confidence);

-- Evolution States: Explicit state for each version
CREATE TABLE IF NOT EXISTS knowledge_evolution_states (
    state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL,
    state TEXT NOT NULL,  -- active, strengthened, weakened, disputed, restricted, superseded, retired
    state_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    effective_from TIMESTAMPTZ DEFAULT now(),
    effective_until TIMESTAMPTZ,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_states_version ON knowledge_evolution_states(version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_states_state ON knowledge_evolution_states(state);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_states_effective ON knowledge_evolution_states(effective_from, effective_until);

-- Knowledge Evidence: Supportive and contradictory evidence
CREATE TABLE IF NOT EXISTS knowledge_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_id UUID,  -- Version this evidence applies to (nullable for general entity evidence)
    evidence_type TEXT NOT NULL,  -- supportive, contradictory, neutral
    source_type TEXT NOT NULL,  -- outcome, feedback, cross_node_evidence, pattern, insight
    source_id UUID NOT NULL,  -- ID of source entity
    source_node_id UUID,  -- Which node provided evidence
    confidence NUMERIC(5,4) NOT NULL,  -- 0-1 confidence
    evidence_data JSONB,  -- Raw evidence content
    created_at TIMESTAMPTZ DEFAULT now(),
    recorded_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_entity ON knowledge_evidence(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_version ON knowledge_evidence(version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_type ON knowledge_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_source ON knowledge_evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_node ON knowledge_evidence(source_node_id);

-- Evolution Rules: Deterministic rules for state transitions
CREATE TABLE IF NOT EXISTS knowledge_evolution_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL UNIQUE,
    rule_type TEXT NOT NULL,  -- strengthening, weakening, restriction, supersession, merging, retirement, dispute
    condition JSONB NOT NULL,  -- Rule conditions (min_evidence, confidence_threshold, etc.)
    action JSONB NOT NULL,  -- Action to take (new_state, create_version, etc.)
    description TEXT,
    enabled BOOLEAN DEFAULT true,
    priority INT DEFAULT 100,  -- Lower number = higher priority
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_rules_type ON knowledge_evolution_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_rules_enabled ON knowledge_evolution_rules(enabled);

-- Evolution Decisions: Record of all evolution evaluations
CREATE TABLE IF NOT EXISTS knowledge_evolution_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_id UUID,
    rule_id UUID,
    decision TEXT NOT NULL,  -- evolved, no_evolution, manual_override, failed_validation
    decision_reason TEXT,
    evidence_considered INT,  -- Count of evidence pieces considered
    evidence_supportive INT,
    evidence_contradictory INT,
    previous_state TEXT,
    resulting_state TEXT,
    resulting_version_id UUID,  -- New version if created
    evaluation_timestamp TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (rule_id) REFERENCES knowledge_evolution_rules(rule_id) ON DELETE SET NULL,
    FOREIGN KEY (resulting_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_decisions_entity ON knowledge_evolution_decisions(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_decisions_version ON knowledge_evolution_decisions(version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_decisions_rule ON knowledge_evolution_decisions(rule_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_decisions_decision ON knowledge_evolution_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_decisions_timestamp ON knowledge_evolution_decisions(evaluation_timestamp);

-- Evolution Transitions: Historical state transitions
CREATE TABLE IF NOT EXISTS knowledge_evolution_transitions (
    transition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_id UUID NOT NULL,
    transition_from TEXT,
    transition_to TEXT NOT NULL,
    decision_id UUID,
    transition_reason TEXT,
    triggered_by_evidence_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE CASCADE,
    FOREIGN KEY (decision_id) REFERENCES knowledge_evolution_decisions(decision_id) ON DELETE SET NULL,
    FOREIGN KEY (triggered_by_evidence_id) REFERENCES knowledge_evidence(evidence_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_transitions_entity ON knowledge_evolution_transitions(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_transitions_version ON knowledge_evolution_transitions(version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_transitions_from_to ON knowledge_evolution_transitions(transition_from, transition_to);

-- Knowledge Lineage: Relationships between knowledge items
CREATE TABLE IF NOT EXISTS knowledge_lineage (
    lineage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id UUID NOT NULL,
    source_version_id UUID,
    target_entity_id UUID NOT NULL,
    target_version_id UUID,
    relationship_type TEXT NOT NULL,  -- derived_from, revises, supersedes, merged_from, restricted_from, contradicts
    lineage_reason TEXT,
    confidence NUMERIC(5,4),  -- Confidence in this relationship
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (source_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (source_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (target_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_source ON knowledge_lineage(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_target ON knowledge_lineage(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_type ON knowledge_lineage(relationship_type);

-- Knowledge Scope Restrictions: Applicability constraints
CREATE TABLE IF NOT EXISTS knowledge_scope_restrictions (
    restriction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_id UUID,
    restriction_type TEXT NOT NULL,  -- constraint, condition, excludes, includes
    scope_criteria JSONB NOT NULL,  -- Conditions for applicability
    applies_to_task_type TEXT,
    excludes_task_type TEXT,
    applies_when_condition TEXT,  -- e.g., "quality_threshold > 0.8"
    restriction_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_scope_restrictions_entity ON knowledge_scope_restrictions(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_scope_restrictions_version ON knowledge_scope_restrictions(version_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_scope_restrictions_task_type ON knowledge_scope_restrictions(applies_to_task_type);

-- Knowledge Dedup Registry: Prevent duplicate processing
CREATE TABLE IF NOT EXISTS knowledge_dedup_registry (
    registry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash TEXT NOT NULL UNIQUE,
    entity_id UUID,
    version_id UUID,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    process_count INT DEFAULT 1,
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE SET NULL,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_dedup_registry_hash ON knowledge_dedup_registry(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_dedup_registry_entity ON knowledge_dedup_registry(entity_id);

-- Knowledge Graph Links: Connect to Section 7 knowledge_artifacts
CREATE TABLE IF NOT EXISTS knowledge_evolution_graph_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    version_id UUID,
    artifact_id UUID NOT NULL,
    link_type TEXT NOT NULL,  -- represents, evolves, restricts, supersedes
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (artifact_id) REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_graph_links_entity ON knowledge_evolution_graph_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_evolution_graph_links_artifact ON knowledge_evolution_graph_links(artifact_id);

-- Memory Version Mapping: Link Section 8 memory to evolved knowledge
CREATE TABLE IF NOT EXISTS knowledge_memory_version_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provenance_id UUID NOT NULL,  -- Section 8 provenance record
    entity_id UUID NOT NULL,
    current_version_id UUID,  -- Current effective version
    previous_version_id UUID,
    link_status TEXT DEFAULT 'active',  -- active, superseded, historical
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (current_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (previous_version_id) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (provenance_id) REFERENCES learning_provenance(provenance_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_memory_version_links_entity ON knowledge_memory_version_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_memory_version_links_provenance ON knowledge_memory_version_links(provenance_id);

-- Knowledge Merge Records: Track knowledge merges
CREATE TABLE IF NOT EXISTS knowledge_merge_records (
    merge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id_1 UUID NOT NULL,
    source_version_id_1 UUID,
    source_entity_id_2 UUID NOT NULL,
    source_version_id_2 UUID,
    target_entity_id UUID NOT NULL,
    target_version_id UUID NOT NULL,
    merge_reason TEXT,
    merge_evidence JSONB,  -- Why they were considered equivalent
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (source_entity_id_1) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (source_version_id_1) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (source_entity_id_2) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (source_version_id_2) REFERENCES knowledge_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (target_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_version_id) REFERENCES knowledge_versions(version_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_merge_records_source_1 ON knowledge_merge_records(source_entity_id_1);
CREATE INDEX IF NOT EXISTS idx_knowledge_merge_records_source_2 ON knowledge_merge_records(source_entity_id_2);
CREATE INDEX IF NOT EXISTS idx_knowledge_merge_records_target ON knowledge_merge_records(target_entity_id);

-- Default Evolution Rules
INSERT INTO knowledge_evolution_rules (rule_name, rule_type, condition, action, description, priority)
VALUES 
  ('min_supportive_evidence_strengthen', 'strengthening', 
   '{"min_supportive_evidence": 3, "supportive_ratio": 0.8, "min_confidence": 0.75}'::jsonb,
   '{"action": "strengthen", "reason": "Multiple independent supportive evidence"}'::jsonb,
   'Knowledge is strengthened when it has 3+ supportive evidence with 80%+ support ratio and 75%+ confidence', 50),
   
  ('contradiction_weaken', 'weakening',
   '{"min_contradictory_evidence": 2, "contradiction_ratio": 0.4, "min_contradiction_confidence": 0.7}'::jsonb,
   '{"action": "weaken", "reason": "Significant contradictory evidence"}'::jsonb,
   'Knowledge is weakened when 40%+ of evidence contradicts it with 70%+ confidence', 60),
   
  ('contradiction_dispute', 'dispute',
   '{"min_supportive": 2, "min_contradictory": 2, "balance_ratio": 0.3, "max_balance_ratio": 0.7}'::jsonb,
   '{"action": "dispute", "reason": "Significant conflicting evidence from multiple sources"}'::jsonb,
   'Knowledge is disputed when 30-70% evidence conflicts and both sides have sufficient support', 70),
   
  ('scope_restriction_from_evidence', 'restriction',
   '{"evidence_pattern": "works_under_condition", "success_rate_general": 0.5, "success_rate_conditional": 0.9}'::jsonb,
   '{"action": "restrict", "reason": "Evidence shows success only under specific conditions"}'::jsonb,
   'Knowledge is restricted when evidence clearly shows it applies only in specific scope', 55),
   
  ('retirement_no_evidence', 'retirement',
   '{"age_days": 365, "no_evidence_count": 0, "supportive_evidence_count": 0}'::jsonb,
   '{"action": "retire", "reason": "No supporting evidence in past 365 days"}'::jsonb,
   'Knowledge is retired when no supporting evidence for 365+ days', 120)
ON CONFLICT (rule_name) DO NOTHING;
