-- Section 14: Strategy / Method Learning
-- Learns which strategies, methods, workflows and approaches work best for particular tasks
-- based on actual execution evidence

-- Strategy Entity: Persistent identity for reusable strategies/methods
CREATE TABLE IF NOT EXISTS strategies (
    strategy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_name TEXT NOT NULL,
    description TEXT,
    domain_applicability TEXT,  -- task type(s) this strategy applies to
    method_representation JSONB,  -- steps, workflow, approach
    constraints JSONB,  -- any constraints
    provenance JSONB,  -- how strategy originated
    lifecycle_state TEXT DEFAULT 'active',  -- active, restricted, superseded, retired
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_strategies_domain ON strategies(domain_applicability);
CREATE INDEX IF NOT EXISTS idx_strategies_state ON strategies(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_strategies_created ON strategies(created_at);

-- Strategy Versions: Preserve evolution of strategies
CREATE TABLE IF NOT EXISTS strategy_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    version_number INT NOT NULL,
    parent_version_id UUID,  -- predecessor version
    method_representation JSONB,
    constraints JSONB,
    creation_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by_node_id UUID,
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_version_id) REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    UNIQUE(strategy_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy ON strategy_versions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_versions_parent ON strategy_versions(parent_version_id);

-- Strategy Execution Record: When a strategy is actually used
CREATE TABLE IF NOT EXISTS strategy_execution_records (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    version_id UUID,
    task_id UUID NOT NULL,
    assignment_id UUID,
    node_id UUID NOT NULL,
    attempt_id UUID,
    execution_timestamp TIMESTAMPTZ DEFAULT now(),
    context JSONB,  -- relevant context
    parameters JSONB,  -- important parameters
    execution_status TEXT,  -- started, in_progress, completed, failed
    completion_status TEXT,  -- success, failure, partial, unknown
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES strategy_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_execution_records_strategy ON strategy_execution_records(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_execution_records_task ON strategy_execution_records(task_id);
CREATE INDEX IF NOT EXISTS idx_strategy_execution_records_node ON strategy_execution_records(node_id);
CREATE INDEX IF NOT EXISTS idx_strategy_execution_records_timestamp ON strategy_execution_records(execution_timestamp);

-- Strategy Evidence: Success/failure evidence from executions
CREATE TABLE IF NOT EXISTS strategy_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    version_id UUID,
    execution_id UUID,
    evidence_type TEXT NOT NULL,  -- success, failure, neutral, insufficient
    outcome_quality NUMERIC(5,4),  -- where available
    verification_result TEXT,  -- passed, failed, inconclusive
    attempts_count INT,
    repair_required BOOLEAN,
    completion BOOLEAN,
    execution_time_seconds INT,
    contradictory_evidence BOOLEAN DEFAULT false,
    confidence NUMERIC(5,4),
    evidence_data JSONB,
    source_node_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES strategy_versions(version_id) ON DELETE SET NULL,
    FOREIGN KEY (execution_id) REFERENCES strategy_execution_records(execution_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_evidence_strategy ON strategy_evidence(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_evidence_type ON strategy_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_strategy_evidence_execution ON strategy_evidence(execution_id);
CREATE INDEX IF NOT EXISTS idx_strategy_evidence_source_node ON strategy_evidence(source_node_id);

-- Strategy Effectiveness: Computed effectiveness scoped to contexts
CREATE TABLE IF NOT EXISTS strategy_effectiveness (
    effectiveness_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    version_id UUID,
    context_scope JSONB,  -- task_type, domain, constraints, etc.
    success_rate NUMERIC(5,4),  -- 0-1
    failure_rate NUMERIC(5,4),  -- 0-1
    evidence_count INT,
    success_count INT,
    failure_count INT,
    neutral_count INT,
    avg_outcome_quality NUMERIC(5,4),
    confidence_level TEXT,  -- high, adequate, low, insufficient
    independent_node_count INT,
    last_updated TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES strategy_versions(version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_effectiveness_strategy ON strategy_effectiveness(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_effectiveness_context ON strategy_effectiveness(context_scope);
CREATE INDEX IF NOT EXISTS idx_strategy_effectiveness_confidence ON strategy_effectiveness(confidence_level);

-- Strategy Comparison: Compare strategies on comparable tasks
CREATE TABLE IF NOT EXISTS strategy_comparisons (
    comparison_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id_1 UUID NOT NULL,
    strategy_id_2 UUID NOT NULL,
    version_id_1 UUID,
    version_id_2 UUID,
    comparison_scope JSONB,  -- which tasks/contexts being compared
    population_count INT,  -- how many tasks/executions compared
    strategy_1_success_rate NUMERIC(5,4),
    strategy_2_success_rate NUMERIC(5,4),
    success_difference NUMERIC(5,4),  -- s1 - s2
    confidence_level TEXT,  -- high, adequate, low, insufficient
    winner_id UUID,  -- UUID of winning strategy, or null if tie
    comparison_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id_1) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id_2) REFERENCES strategies(strategy_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_strategy_comparisons_strategy_1 ON strategy_comparisons(strategy_id_1);
CREATE INDEX IF NOT EXISTS idx_strategy_comparisons_strategy_2 ON strategy_comparisons(strategy_id_2);

-- Strategy Repairs: Track repairs applied to failures
CREATE TABLE IF NOT EXISTS strategy_repairs (
    repair_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL,
    strategy_id UUID NOT NULL,
    failure_reason TEXT,
    repair_action TEXT,
    repair_applied_at TIMESTAMPTZ,
    subsequent_result TEXT,  -- success, failure, partial
    repair_effectiveness NUMERIC(5,4),
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (execution_id) REFERENCES strategy_execution_records(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_strategy_repairs_execution ON strategy_repairs(execution_id);
CREATE INDEX IF NOT EXISTS idx_strategy_repairs_strategy ON strategy_repairs(strategy_id);

-- Strategy Variants: Track variants of strategies
CREATE TABLE IF NOT EXISTS strategy_variants (
    variant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_strategy_id UUID NOT NULL,
    variant_strategy_id UUID NOT NULL,
    variant_type TEXT,  -- specialization, optimization, alternate, etc.
    lineage_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (parent_strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (variant_strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_strategy_variants_parent ON strategy_variants(parent_strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_variants_variant ON strategy_variants(variant_strategy_id);

-- Strategy Selection Observations: Record when strategies are considered/selected/rejected
CREATE TABLE IF NOT EXISTS strategy_selection_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL,
    assignment_id UUID,
    node_id UUID,
    strategy_id UUID NOT NULL,
    observation_type TEXT NOT NULL,  -- considered, selected, rejected, executed, evaluated
    rationale TEXT,
    context JSONB,
    timestamp TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_strategy_selection_observations_task ON strategy_selection_observations(task_id);
CREATE INDEX IF NOT EXISTS idx_strategy_selection_observations_strategy ON strategy_selection_observations(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_selection_observations_type ON strategy_selection_observations(observation_type);

-- Strategy Guidance Cache: Pre-computed guidance for tasks
CREATE TABLE IF NOT EXISTS strategy_guidance_cache (
    cache_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    domain TEXT,
    guidance_data JSONB,  -- structured guidance with strategies, evidence, cautions
    relevance_score NUMERIC(5,4),
    last_updated TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_strategy_guidance_cache_task_type ON strategy_guidance_cache(task_type);
CREATE INDEX IF NOT EXISTS idx_strategy_guidance_cache_domain ON strategy_guidance_cache(domain);

-- Strategy Graph Links: Connect strategies to knowledge graph
CREATE TABLE IF NOT EXISTS strategy_graph_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    artifact_id UUID,  -- link to Section 7 knowledge_artifacts
    link_type TEXT,  -- implements, uses, references, relates_to
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (artifact_id) REFERENCES knowledge_artifacts(artifact_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_graph_links_strategy ON strategy_graph_links(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_graph_links_artifact ON strategy_graph_links(artifact_id);

-- Strategy Memory Links: Connect strategies to organizational memory
CREATE TABLE IF NOT EXISTS strategy_memory_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL,
    provenance_id UUID,  -- link to Section 8 learning_provenance
    effectiveness_id UUID,  -- link to strategy_effectiveness
    link_status TEXT DEFAULT 'active',  -- active, superseded, historical
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE CASCADE,
    FOREIGN KEY (provenance_id) REFERENCES learning_provenance(provenance_id) ON DELETE SET NULL,
    FOREIGN KEY (effectiveness_id) REFERENCES strategy_effectiveness(effectiveness_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_memory_links_strategy ON strategy_memory_links(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_memory_links_provenance ON strategy_memory_links(provenance_id);

-- Strategy Dedup Registry: Prevent duplicate processing
CREATE TABLE IF NOT EXISTS strategy_dedup_registry (
    registry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_hash TEXT NOT NULL UNIQUE,
    strategy_id UUID,
    execution_id UUID,
    evidence_id UUID,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    process_count INT DEFAULT 1,
    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id) ON DELETE SET NULL,
    FOREIGN KEY (execution_id) REFERENCES strategy_execution_records(execution_id) ON DELETE SET NULL,
    FOREIGN KEY (evidence_id) REFERENCES strategy_evidence(evidence_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_dedup_registry_hash ON strategy_dedup_registry(content_hash);
