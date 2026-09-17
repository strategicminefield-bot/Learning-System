-- Section 8: Learning Memory Integration and Automatic Graph Population

-- Track learning event provenance
CREATE TABLE IF NOT EXISTS learning_provenance (
    provenance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL, -- outcome, pattern, insight, artifact
    source_id UUID NOT NULL, -- task_outcome_id, pattern_id, insight_id, artifact_id
    node_id UUID, -- originating worker
    task_type TEXT,
    task_id UUID REFERENCES tasks(task_id) ON DELETE SET NULL,
    outcome_id UUID REFERENCES task_outcomes(outcome_id) ON DELETE SET NULL,
    confidence FLOAT DEFAULT 0.8,
    evidence_count INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON learning_provenance(source_type);
CREATE INDEX ON learning_provenance(source_id);
CREATE INDEX ON learning_provenance(node_id);
CREATE INDEX ON learning_provenance(task_type);
CREATE INDEX ON learning_provenance(outcome_id);

-- Track graph node creation from learning
CREATE TABLE IF NOT EXISTS memory_graph_links (
    link_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provenance_id UUID NOT NULL REFERENCES learning_provenance(provenance_id) ON DELETE CASCADE,
    graph_entity_id UUID NOT NULL, -- artifact_id or relationship_id from knowledge_relationships
    graph_entity_type TEXT NOT NULL, -- artifact, relationship
    sync_status TEXT DEFAULT 'synced', -- pending, synced, failed
    sync_error TEXT,
    last_sync TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON memory_graph_links(provenance_id);
CREATE INDEX ON memory_graph_links(graph_entity_id);
CREATE INDEX ON memory_graph_links(sync_status);

-- Task → Outcome → Memory traceability
CREATE TABLE IF NOT EXISTS memory_trace (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES assignments(assignment_id) ON DELETE SET NULL,
    outcome_id UUID REFERENCES task_outcomes(outcome_id) ON DELETE CASCADE,
    node_id UUID NOT NULL,
    learning_events JSONB DEFAULT '[]'::JSONB, -- array of {type, id, created_at}
    graph_entities JSONB DEFAULT '[]'::JSONB, -- array of {type, id}
    trace_status TEXT DEFAULT 'processing', -- processing, complete, error
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON memory_trace(task_id);
CREATE INDEX ON memory_trace(outcome_id);
CREATE INDEX ON memory_trace(node_id);
CREATE INDEX ON memory_trace(trace_status);

-- Learning deduplication registry
CREATE TABLE IF NOT EXISTS learning_dedup_registry (
    registry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_hash TEXT NOT NULL UNIQUE, -- hash of learning event
    source_type TEXT NOT NULL,
    source_id UUID NOT NULL,
    canonical_id UUID, -- canonical learning event if already processed
    first_seen TIMESTAMPTZ DEFAULT now(),
    reprocess_count INT DEFAULT 0,
    last_reprocess TIMESTAMPTZ
);

CREATE INDEX ON learning_dedup_registry(source_hash);
CREATE INDEX ON learning_dedup_registry(source_type);
CREATE INDEX ON learning_dedup_registry(canonical_id);

-- Outcome → Graph mapping for automatic vector memory population
CREATE TABLE IF NOT EXISTS outcome_graph_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outcome_id UUID NOT NULL REFERENCES task_outcomes(outcome_id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE,
    mapping_type TEXT NOT NULL, -- solution, template, approach, anti_pattern
    auto_created BOOLEAN DEFAULT true,
    quality_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON outcome_graph_mappings(outcome_id);
CREATE INDEX ON outcome_graph_mappings(artifact_id);
CREATE INDEX ON outcome_graph_mappings(auto_created);

-- Add columns to existing tables if needed
ALTER TABLE performance_insights ADD COLUMN IF NOT EXISTS provenance_id UUID REFERENCES learning_provenance(provenance_id) ON DELETE SET NULL;
ALTER TABLE performance_insights ADD COLUMN IF NOT EXISTS evidence_links JSONB DEFAULT '[]'::JSONB;
ALTER TABLE result_patterns ADD COLUMN IF NOT EXISTS provenance_id UUID REFERENCES learning_provenance(provenance_id) ON DELETE SET NULL;
ALTER TABLE result_patterns ADD COLUMN IF NOT EXISTS source_outcome_ids UUID[] DEFAULT '{}'::UUID[];

CREATE INDEX ON performance_insights(provenance_id);
CREATE INDEX ON result_patterns(provenance_id);
