-- Section 7: Knowledge Graph and Vector Memory Layer

-- Vector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Knowledge graph relationships
CREATE TABLE knowledge_relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_artifact_id UUID NOT NULL REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE,
    target_artifact_id UUID NOT NULL REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL, -- 'related_to', 'extends', 'contradicts', 'prerequisite', 'applies_to'
    strength FLOAT DEFAULT 0.5, -- 0-1 relationship strength
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_artifact_id, target_artifact_id, relationship_type)
);

CREATE INDEX ON knowledge_relationships(source_artifact_id);
CREATE INDEX ON knowledge_relationships(target_artifact_id);
CREATE INDEX ON knowledge_relationships(relationship_type);

-- Vector embeddings for artifacts
CREATE TABLE artifact_embeddings (
    embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_id UUID NOT NULL REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE UNIQUE,
    embedding vector(1536), -- OpenAI embedding dimension
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON artifact_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON artifact_embeddings(artifact_id);

-- Task type to knowledge mappings
CREATE TABLE task_knowledge_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    artifact_id UUID NOT NULL REFERENCES knowledge_artifacts(artifact_id) ON DELETE CASCADE,
    relevance_score FLOAT DEFAULT 0.8, -- How relevant this artifact is to task type
    usage_in_task_count INT DEFAULT 0, -- Times this artifact was used for this task type
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(task_type, artifact_id)
);

CREATE INDEX ON task_knowledge_mappings(task_type);
CREATE INDEX ON task_knowledge_mappings(artifact_id);

-- Knowledge search history for analytics
CREATE TABLE knowledge_searches (
    search_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID,
    query TEXT NOT NULL,
    query_embedding vector(1536),
    results_count INT,
    query_type TEXT, -- 'semantic', 'keyword', 'by_type'
    task_type TEXT,
    selected_artifact_id UUID REFERENCES knowledge_artifacts(artifact_id) ON DELETE SET NULL,
    useful BOOLEAN, -- Whether result was useful
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON knowledge_searches(node_id);
CREATE INDEX ON knowledge_searches(query_type);
CREATE INDEX ON knowledge_searches(task_type);
CREATE INDEX ON knowledge_searches(created_at DESC);

-- Knowledge graph metrics for discovery
CREATE TABLE knowledge_graph_stats (
    stat_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name TEXT NOT NULL,
    task_type TEXT,
    artifact_count INT,
    relationship_count INT,
    avg_connections_per_artifact FLOAT,
    search_volume_24h INT,
    most_used_artifact_id UUID REFERENCES knowledge_artifacts(artifact_id) ON DELETE SET NULL,
    least_used_artifact_id UUID REFERENCES knowledge_artifacts(artifact_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(metric_name, COALESCE(task_type, 'global'))
);

CREATE INDEX ON knowledge_graph_stats(task_type);
CREATE INDEX ON knowledge_graph_stats(created_at DESC);

-- Add embedding columns to existing knowledge_artifacts if not exists
ALTER TABLE knowledge_artifacts ADD COLUMN IF NOT EXISTS embedding vector(1536);
ALTER TABLE knowledge_artifacts ADD COLUMN IF NOT EXISTS semantic_tags TEXT[] DEFAULT '{}'::TEXT[];
ALTER TABLE knowledge_artifacts ADD COLUMN IF NOT EXISTS search_text TSVECTOR;

-- Create index for full-text search
CREATE INDEX IF NOT EXISTS idx_knowledge_search_text ON knowledge_artifacts USING GIN (search_text);
