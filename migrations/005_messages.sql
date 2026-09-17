BEGIN;

-- Messages table for inter-worker communication
CREATE TABLE IF NOT EXISTS messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_node_id UUID NOT NULL REFERENCES nodes(node_id),
    recipient_node_id UUID REFERENCES nodes(node_id),
    task_id UUID REFERENCES tasks(task_id),
    assignment_id UUID REFERENCES assignments(assignment_id),
    message_type TEXT NOT NULL,
    subject TEXT,
    content JSONB NOT NULL DEFAULT '{}'::jsonb,
    priority INTEGER DEFAULT 0,
    read_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ
);

-- Message subscriptions for topic-based messaging
CREATE TABLE IF NOT EXISTS message_subscriptions (
    subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    topic TEXT NOT NULL,
    filter_criteria JSONB,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(node_id, topic)
);

-- Task notifications for task state changes
CREATE TABLE IF NOT EXISTS task_notifications (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    notification_type TEXT NOT NULL,
    detail JSONB,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_node_id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_node_id);
CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);
CREATE INDEX IF NOT EXISTS idx_messages_assignment ON messages(assignment_id);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_recipient_status ON messages(recipient_node_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_node ON message_subscriptions(node_id, active);
CREATE INDEX IF NOT EXISTS idx_subscriptions_topic ON message_subscriptions(topic);
CREATE INDEX IF NOT EXISTS idx_task_notifications_task ON task_notifications(task_id);
CREATE INDEX IF NOT EXISTS idx_task_notifications_node ON task_notifications(node_id);
CREATE INDEX IF NOT EXISTS idx_task_notifications_created ON task_notifications(created_at DESC);

COMMIT;
