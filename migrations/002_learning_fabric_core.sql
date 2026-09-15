BEGIN;

CREATE TABLE IF NOT EXISTS workflows (
    workflow_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES requests(request_id),
    workflow_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    objective JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(workflow_id),
    parent_task_id UUID REFERENCES tasks(task_id),
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    specification JSONB NOT NULL DEFAULT '{}'::jsonb,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    depends_on_task_id UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL DEFAULT 'blocks',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    status TEXT NOT NULL DEFAULT 'assigned',
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    assignment_id UUID REFERENCES assignments(assignment_id),
    node_id UUID REFERENCES nodes(node_id),
    attempt_number INTEGER NOT NULL,
    method JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (task_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID NOT NULL REFERENCES attempts(attempt_id),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID REFERENCES nodes(node_id),
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_score NUMERIC,
    status TEXT NOT NULL DEFAULT 'recorded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id UUID REFERENCES attempts(attempt_id),
    result_id UUID REFERENCES results(result_id),
    observation_type TEXT NOT NULL,
    content JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT,
    confidence NUMERIC,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflows_request ON workflows(request_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workflow ON tasks(workflow_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_assignments_task_status ON assignments(task_id, status);
CREATE INDEX IF NOT EXISTS idx_assignments_node_status ON assignments(node_id, status);
CREATE INDEX IF NOT EXISTS idx_attempts_task ON attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_results_task ON results(task_id);
CREATE INDEX IF NOT EXISTS idx_observations_attempt ON observations(attempt_id);

COMMIT;
