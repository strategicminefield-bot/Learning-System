-- Section 9: Retrieval & Context Layer
-- Stores retrieval queries, traces, and context assembly metadata
-- Enables task-aware access to prior learning without manual knowledge selection

-- Retrieval query log: what was requested
CREATE TABLE retrieval_queries (
    query_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID REFERENCES nodes(node_id),
    assignment_id UUID REFERENCES assignments(assignment_id),
    query_params JSONB NOT NULL,
    query_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Retrieval trace: complete record of what was retrieved and why
CREATE TABLE retrieval_traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id UUID NOT NULL REFERENCES retrieval_queries(query_id),
    
    -- What was considered
    outcomes_considered INTEGER DEFAULT 0,
    patterns_considered INTEGER DEFAULT 0,
    insights_considered INTEGER DEFAULT 0,
    artifacts_considered INTEGER DEFAULT 0,
    graph_entities_considered INTEGER DEFAULT 0,
    
    -- What was selected
    outcomes_selected INTEGER DEFAULT 0,
    patterns_selected INTEGER DEFAULT 0,
    insights_selected INTEGER DEFAULT 0,
    artifacts_selected INTEGER DEFAULT 0,
    graph_entities_selected INTEGER DEFAULT 0,
    
    -- Context metrics
    total_items_returned INTEGER DEFAULT 0,
    total_context_size_bytes INTEGER DEFAULT 0,
    
    -- Ranking and deduplication
    deduplication_count INTEGER DEFAULT 0,
    filtered_by_threshold INTEGER DEFAULT 0,
    
    -- Trace metadata
    trace_status TEXT DEFAULT 'complete', -- complete, error, partial
    trace_error TEXT,
    execution_time_ms INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Individual retrieved item record: one per memory item returned
CREATE TABLE retrieved_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL REFERENCES retrieval_traces(trace_id),
    
    -- Source identification
    source_type TEXT NOT NULL, -- outcome, pattern, insight, artifact, graph_entity
    source_id UUID NOT NULL,
    
    -- Provenance
    provenance_id UUID REFERENCES learning_provenance(provenance_id),
    
    -- Ranking
    relevance_score NUMERIC(5,4) DEFAULT 0.5000, -- 0-1 relevance
    ranking_factors JSONB, -- {vector_similarity, task_type_match, confidence, recency, ...}
    
    -- Item metadata
    item_metadata JSONB, -- Content summary, type, etc
    
    -- Deduplication
    is_duplicate BOOLEAN DEFAULT FALSE,
    canonical_item_id UUID, -- If duplicate, points to first occurrence
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Context package: structured output delivered to node
CREATE TABLE context_packages (
    package_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL REFERENCES retrieval_traces(trace_id),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID REFERENCES nodes(node_id),
    
    -- Complete context structure
    context_data JSONB NOT NULL, -- {outcomes: [], patterns: [], insights: [], artifacts: [], graph: [], provenance: []}
    context_size_bytes INTEGER,
    item_count INTEGER,
    
    -- Metadata
    package_format TEXT DEFAULT 'v1', -- For versioning
    assembly_time_ms INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Retrieval feedback: did the retrieved context help?
CREATE TABLE retrieval_feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    package_id UUID NOT NULL REFERENCES context_packages(package_id),
    
    -- Node assessment
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    usefulness_score NUMERIC(5,4), -- 0-1, node's assessment of usefulness
    
    -- Whether retrieved learning was actually used
    used_items JSONB, -- Array of item_ids that were referenced/used
    
    -- Outcome correlation (for Section 10)
    assignment_id UUID REFERENCES assignments(assignment_id),
    outcome_id UUID REFERENCES task_outcomes(outcome_id),
    
    -- Feedback metadata
    feedback_text TEXT,
    feedback_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Retrieval configuration: thresholds and limits per context type
CREATE TABLE retrieval_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Per-source limits
    max_outcomes INTEGER DEFAULT 5,
    max_patterns INTEGER DEFAULT 3,
    max_insights INTEGER DEFAULT 3,
    max_artifacts INTEGER DEFAULT 5,
    max_graph_entities INTEGER DEFAULT 10,
    
    -- Relevance thresholds
    min_outcome_confidence NUMERIC(5,4) DEFAULT 0.5000,
    min_pattern_success_rate NUMERIC(5,4) DEFAULT 0.6000,
    min_insight_confidence NUMERIC(5,4) DEFAULT 0.5000,
    min_artifact_quality NUMERIC(5,4) DEFAULT 0.5000,
    
    -- Context size control
    max_total_items INTEGER DEFAULT 25,
    max_context_size_bytes INTEGER DEFAULT 1000000, -- 1MB
    
    -- Recency
    max_age_days INTEGER DEFAULT 90,
    
    -- Deduplication
    deduplicate_by_source BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_retrieval_queries_task ON retrieval_queries(task_id);
CREATE INDEX idx_retrieval_queries_node ON retrieval_queries(node_id);
CREATE INDEX idx_retrieval_queries_created ON retrieval_queries(created_at DESC);

CREATE INDEX idx_retrieval_traces_query ON retrieval_traces(query_id);
CREATE INDEX idx_retrieval_traces_created ON retrieval_traces(created_at DESC);
CREATE INDEX idx_retrieval_traces_status ON retrieval_traces(trace_status);

CREATE INDEX idx_retrieved_items_trace ON retrieved_items(trace_id);
CREATE INDEX idx_retrieved_items_source ON retrieved_items(source_type, source_id);
CREATE INDEX idx_retrieved_items_provenance ON retrieved_items(provenance_id);

CREATE INDEX idx_context_packages_trace ON context_packages(trace_id);
CREATE INDEX idx_context_packages_task ON context_packages(task_id);
CREATE INDEX idx_context_packages_node ON context_packages(node_id);
CREATE INDEX idx_context_packages_created ON context_packages(created_at DESC);

CREATE INDEX idx_retrieval_feedback_package ON retrieval_feedback(package_id);
CREATE INDEX idx_retrieval_feedback_node ON retrieval_feedback(node_id);
CREATE INDEX idx_retrieval_feedback_outcome ON retrieval_feedback(outcome_id);

-- Insert default retrieval config
INSERT INTO retrieval_config (config_id) VALUES (gen_random_uuid());
