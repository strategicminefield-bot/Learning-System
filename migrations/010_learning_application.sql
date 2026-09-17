-- Section 10: Learning Application Layer
-- Tracks which learning items are applied to attempts and execution guidance

-- Applied learning: record of learning selected for an attempt
CREATE TABLE applied_learning (
    applied_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    
    -- Source identification
    retrieval_trace_id UUID REFERENCES retrieval_traces(trace_id),
    context_package_id UUID REFERENCES context_packages(package_id),
    
    -- Learning item applied
    learning_type TEXT NOT NULL, -- outcome, pattern, insight, artifact, graph_entity
    learning_id UUID NOT NULL,
    provenance_id UUID REFERENCES learning_provenance(provenance_id),
    
    -- Application metadata
    relevance_score NUMERIC(5,4), -- Ranking score from retrieval
    confidence NUMERIC(5,4), -- Confidence in applicability
    applicability_reason TEXT, -- Why this learning was selected
    
    -- Evidence and provenance
    source_task_id UUID REFERENCES tasks(task_id),
    source_outcome_id UUID REFERENCES task_outcomes(outcome_id),
    source_node_id UUID REFERENCES nodes(node_id),
    
    -- Application status
    status TEXT DEFAULT 'applied', -- applied, rejected, failed, superseded
    status_reason TEXT,
    
    -- Timing
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Execution guidance: structured guidance for worker execution
CREATE TABLE execution_guidance (
    guidance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id) UNIQUE,
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    
    -- Guidance components
    recommended_approaches JSONB, -- Array of recommended methods
    known_patterns JSONB, -- Array of discovered patterns
    warnings JSONB, -- Array of warnings/known failures
    constraints JSONB, -- Array of constraints or limitations
    insights JSONB, -- Array of performance insights
    useful_knowledge JSONB, -- Array of useful artifacts/templates
    
    -- Source metadata
    retrieval_trace_id UUID REFERENCES retrieval_traces(trace_id),
    applied_learning_count INTEGER DEFAULT 0,
    
    -- Guidance snapshot (immutable)
    guidance_data JSONB NOT NULL, -- Complete guidance structure
    guidance_version TEXT DEFAULT 'v1',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ, -- Optional expiration
    
    -- Metadata
    total_items INTEGER DEFAULT 0,
    guidance_quality_score NUMERIC(5,4), -- Composite quality of guidance
    generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Application decision log: why learning was selected/rejected
CREATE TABLE application_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    
    -- What was considered
    considered_learning_id UUID NOT NULL,
    considered_type TEXT NOT NULL,
    
    -- Decision
    decision TEXT NOT NULL, -- applied, rejected, conditional
    reason TEXT,
    
    -- Scoring
    relevance_score NUMERIC(5,4),
    confidence_score NUMERIC(5,4),
    applicability_score NUMERIC(5,4),
    
    -- Context
    decision_factors JSONB, -- Decision rationale
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Guidance application trace: complete audit trail
CREATE TABLE guidance_traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guidance_id UUID NOT NULL REFERENCES execution_guidance(guidance_id),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    
    -- Retrieval to guidance pipeline
    retrieval_trace_id UUID REFERENCES retrieval_traces(trace_id),
    learning_items_considered INTEGER DEFAULT 0,
    learning_items_applied INTEGER DEFAULT 0,
    learning_items_rejected INTEGER DEFAULT 0,
    
    -- Application statistics
    total_decisions INTEGER DEFAULT 0,
    applied_decisions INTEGER DEFAULT 0,
    rejected_decisions INTEGER DEFAULT 0,
    
    -- Generation metrics
    generation_time_ms INTEGER,
    total_guidance_size_bytes INTEGER,
    
    -- Status
    trace_status TEXT DEFAULT 'complete', -- complete, partial, error
    trace_error TEXT,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Application configuration: selectivity and limits
CREATE TABLE application_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Application selectivity
    min_relevance_threshold NUMERIC(5,4) DEFAULT 0.6000,
    min_confidence_threshold NUMERIC(5,4) DEFAULT 0.6000,
    min_applicability_score NUMERIC(5,4) DEFAULT 0.5000,
    
    -- Per-type application
    apply_outcomes BOOLEAN DEFAULT TRUE,
    apply_patterns BOOLEAN DEFAULT TRUE,
    apply_insights BOOLEAN DEFAULT TRUE,
    apply_artifacts BOOLEAN DEFAULT TRUE,
    apply_graph_entities BOOLEAN DEFAULT TRUE,
    
    -- Guidance composition
    include_warnings BOOLEAN DEFAULT TRUE,
    include_constraints BOOLEAN DEFAULT TRUE,
    max_recommended_approaches INTEGER DEFAULT 5,
    max_warnings INTEGER DEFAULT 3,
    max_constraints INTEGER DEFAULT 3,
    
    -- Conflict handling
    handle_conflicting_learning TEXT DEFAULT 'present_both', -- present_both, highest_confidence, reject_all
    
    -- Deduplication
    deduplicate_guidance BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Worker guidance access log: what was retrieved
CREATE TABLE worker_guidance_access (
    access_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guidance_id UUID NOT NULL REFERENCES execution_guidance(guidance_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    
    -- Access metadata
    accessed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    full_guidance_retrieved BOOLEAN DEFAULT FALSE,
    partial_guidance_retrieved BOOLEAN DEFAULT FALSE,
    guidance_size_bytes INTEGER,
    
    -- Tracking
    access_count INTEGER DEFAULT 1,
    last_accessed_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_applied_learning_attempt ON applied_learning(attempt_id);
CREATE INDEX idx_applied_learning_learning_id ON applied_learning(learning_type, learning_id);
CREATE INDEX idx_applied_learning_provenance ON applied_learning(provenance_id);
CREATE INDEX idx_applied_learning_status ON applied_learning(status);
CREATE INDEX idx_applied_learning_created ON applied_learning(created_at DESC);

CREATE INDEX idx_execution_guidance_attempt ON execution_guidance(attempt_id);
CREATE INDEX idx_execution_guidance_task ON execution_guidance(task_id);
CREATE INDEX idx_execution_guidance_node ON execution_guidance(node_id);
CREATE INDEX idx_execution_guidance_created ON execution_guidance(created_at DESC);

CREATE INDEX idx_application_decisions_attempt ON application_decisions(attempt_id);
CREATE INDEX idx_application_decisions_decision ON application_decisions(decision);
CREATE INDEX idx_application_decisions_created ON application_decisions(created_at DESC);

CREATE INDEX idx_guidance_traces_guidance ON guidance_traces(guidance_id);
CREATE INDEX idx_guidance_traces_attempt ON guidance_traces(attempt_id);
CREATE INDEX idx_guidance_traces_retrieval ON guidance_traces(retrieval_trace_id);
CREATE INDEX idx_guidance_traces_created ON guidance_traces(created_at DESC);

CREATE INDEX idx_worker_guidance_access_guidance ON worker_guidance_access(guidance_id);
CREATE INDEX idx_worker_guidance_access_node ON worker_guidance_access(node_id);
CREATE INDEX idx_worker_guidance_access_attempt ON worker_guidance_access(attempt_id);

-- Insert default application config
INSERT INTO application_config (config_id) VALUES (gen_random_uuid());
