BEGIN;

-- Result patterns for learning from outcomes
CREATE TABLE IF NOT EXISTS result_patterns (
    pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    pattern_rule JSONB NOT NULL,
    success_rate DECIMAL(5, 4),
    occurrence_count INTEGER DEFAULT 0,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Worker learning profiles
CREATE TABLE IF NOT EXISTS worker_learning (
    learning_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    task_type TEXT,
    skill_area TEXT,
    proficiency_score DECIMAL(5, 4) DEFAULT 0.5,
    tasks_completed INTEGER DEFAULT 0,
    success_rate DECIMAL(5, 4),
    avg_time_seconds INTEGER,
    quality_score DECIMAL(5, 4),
    last_updated TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(node_id, task_type, skill_area)
);

-- Task outcome analysis
CREATE TABLE IF NOT EXISTS task_outcomes (
    outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    assignment_id UUID REFERENCES assignments(assignment_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    outcome_status TEXT NOT NULL,
    quality_score DECIMAL(5, 4),
    execution_time_seconds INTEGER,
    result_summary JSONB,
    learning_points JSONB,
    patterns_matched UUID[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Knowledge artifacts from successful tasks
CREATE TABLE IF NOT EXISTS knowledge_artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    node_id UUID REFERENCES nodes(node_id),
    artifact_type TEXT NOT NULL,
    content JSONB NOT NULL,
    quality_score DECIMAL(5, 4),
    usage_count INTEGER DEFAULT 0,
    effectiveness_rating DECIMAL(5, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

-- Performance insights and recommendations
CREATE TABLE IF NOT EXISTS performance_insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID REFERENCES nodes(node_id),
    task_type TEXT,
    insight_type TEXT NOT NULL,
    description TEXT,
    recommendation JSONB,
    confidence_score DECIMAL(5, 4),
    evidence_count INTEGER DEFAULT 0,
    actionable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_patterns_task_type ON result_patterns(task_type);
CREATE INDEX IF NOT EXISTS idx_patterns_created ON result_patterns(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_patterns_success ON result_patterns(success_rate DESC);
CREATE INDEX IF NOT EXISTS idx_worker_learning_node ON worker_learning(node_id);
CREATE INDEX IF NOT EXISTS idx_worker_learning_task_type ON worker_learning(task_type);
CREATE INDEX IF NOT EXISTS idx_worker_learning_proficiency ON worker_learning(proficiency_score DESC);
CREATE INDEX IF NOT EXISTS idx_task_outcomes_task ON task_outcomes(task_id);
CREATE INDEX IF NOT EXISTS idx_task_outcomes_node ON task_outcomes(node_id);
CREATE INDEX IF NOT EXISTS idx_task_outcomes_status ON task_outcomes(outcome_status);
CREATE INDEX IF NOT EXISTS idx_task_outcomes_created ON task_outcomes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_artifacts_type ON knowledge_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_artifacts_task_type ON knowledge_artifacts(task_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_artifacts_quality ON knowledge_artifacts(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_insights_node ON performance_insights(node_id);
CREATE INDEX IF NOT EXISTS idx_insights_type ON performance_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_insights_task_type ON performance_insights(task_type);
CREATE INDEX IF NOT EXISTS idx_insights_actionable ON performance_insights(actionable);

COMMIT;
