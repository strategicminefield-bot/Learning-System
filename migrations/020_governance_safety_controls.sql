-- ============================================================================
-- MIGRATION 020: GOVERNANCE & SAFETY CONTROLS LAYER
-- ============================================================================
-- 
-- This migration implements a complete governance and safety controls system
-- for autonomous/adaptive capabilities created in Sections 15-19.
--
-- Core principles:
-- 1. All protected actions must pass governance evaluation before execution
-- 2. Authority is NOT inferred from capability, role, or success history
-- 3. Explicit user/task constraints outrank learned preferences
-- 4. Governance decisions are immutable and auditable
-- 5. Authority can be revoked; historical decisions are preserved
-- 6. Policies are versioned; decisions reference exact policy versions used
-- 7. Provider-agnostic: governance applies consistently to all node types
-- 8. No silent infrastructure provisioning, permission escalation, or policy weakening
--
-- ============================================================================

-- ============================================================================
-- 1. GOVERNANCE ACTORS (Who can make decisions)
-- ============================================================================

CREATE TABLE governance_actors (
  actor_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Identity and type
  actor_type TEXT NOT NULL,  -- human, ai_node, node_instance, service, automated_process, organisation_team
  actor_reference TEXT NOT NULL,  -- Human name, node ID, service name, etc.
  
  -- State
  state TEXT DEFAULT 'active',  -- active, inactive, restricted, retired, suspended
  
  -- Provenance
  created_at TIMESTAMPTZ DEFAULT NOW(),
  created_by_actor_id UUID REFERENCES governance_actors(actor_id),
  last_activity_at TIMESTAMPTZ,
  
  CONSTRAINT valid_actor_type CHECK (actor_type IN (
    'human', 'ai_node', 'node_instance', 'service', 'automated_process', 'organisation_team'
  )),
  CONSTRAINT valid_actor_state CHECK (state IN (
    'active', 'inactive', 'restricted', 'retired', 'suspended'
  )),
  UNIQUE(actor_type, actor_reference)
);

CREATE INDEX idx_governance_actors_type ON governance_actors(actor_type);
CREATE INDEX idx_governance_actors_state ON governance_actors(state);
CREATE INDEX idx_governance_actors_created ON governance_actors(created_at DESC);

-- ============================================================================
-- 2. PROTECTED ACTIONS (What actions are governed)
-- ============================================================================

CREATE TABLE protected_actions (
  action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  action_code TEXT NOT NULL UNIQUE,  -- task_execution, strategy_application, experiment_creation, learning_promotion, node_definition_change, node_activation, node_provisioning_request, node_retirement, org_restructuring, role_assignment, external_tool_use, database_mutation, infrastructure_change_request, authority_change, config_change, external_side_effect
  
  name TEXT NOT NULL,
  description TEXT,
  
  -- Risk/impact level
  risk_level TEXT DEFAULT 'medium',  -- low, medium, high, critical
  
  -- Defaults
  default_effect TEXT DEFAULT 'REQUIRE_APPROVAL',  -- ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT valid_risk_level CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
  CONSTRAINT valid_default_effect CHECK (default_effect IN ('ALLOW', 'ALLOW_WITH_CONSTRAINTS', 'REQUIRE_APPROVAL', 'DENY'))
);

CREATE INDEX idx_protected_actions_code ON protected_actions(action_code);
CREATE INDEX idx_protected_actions_risk ON protected_actions(risk_level);

-- Pre-populate protected actions
INSERT INTO protected_actions (action_code, name, description, risk_level, default_effect) VALUES
  ('task_execution', 'Task Execution', 'Execute a task', 'medium', 'ALLOW'),
  ('strategy_application', 'Strategy Application', 'Apply a strategy to a task', 'medium', 'ALLOW'),
  ('orchestration_decision', 'Orchestration Decision', 'Make adaptive orchestration decision', 'high', 'ALLOW'),
  ('experiment_creation', 'Experiment Creation', 'Create a controlled experiment', 'high', 'REQUIRE_APPROVAL'),
  ('learning_promotion', 'Learning Promotion', 'Promote validated learning to active use', 'high', 'REQUIRE_APPROVAL'),
  ('node_definition_change', 'Node Definition Change', 'Modify node definition', 'critical', 'REQUIRE_APPROVAL'),
  ('node_activation', 'Node Activation', 'Activate or enable a node', 'high', 'REQUIRE_APPROVAL'),
  ('node_provisioning_request', 'Node Provisioning Request', 'Request new node provisioning', 'critical', 'REQUIRE_APPROVAL'),
  ('node_retirement', 'Node Retirement', 'Retire or disable a node', 'high', 'REQUIRE_APPROVAL'),
  ('org_restructuring', 'Organisational Restructuring', 'Change organisational structure', 'high', 'REQUIRE_APPROVAL'),
  ('role_assignment', 'Role Assignment', 'Assign role to team member', 'medium', 'ALLOW'),
  ('external_tool_use', 'External Tool Use', 'Use external tools or APIs', 'high', 'REQUIRE_APPROVAL'),
  ('database_mutation', 'Database Mutation', 'Modify core system data', 'critical', 'REQUIRE_APPROVAL'),
  ('infrastructure_change_request', 'Infrastructure Change Request', 'Request infrastructure changes', 'critical', 'REQUIRE_APPROVAL'),
  ('authority_change', 'Authority Change', 'Modify authority or permissions', 'critical', 'REQUIRE_APPROVAL'),
  ('config_change', 'Configuration Change', 'Modify system configuration', 'high', 'REQUIRE_APPROVAL'),
  ('external_side_effect', 'External Side Effect', 'External communication or action', 'high', 'REQUIRE_APPROVAL'),
  ('emergency_restriction', 'Emergency Restriction', 'Activate emergency restrictions', 'critical', 'REQUIRE_APPROVAL'),
  ('policy_modification', 'Policy Modification', 'Modify governance policies', 'critical', 'REQUIRE_APPROVAL')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 3. GOVERNANCE POLICIES (Rules governing actions)
-- ============================================================================

CREATE TABLE governance_policies (
  policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  name TEXT NOT NULL,
  description TEXT,
  
  -- Versioning
  policy_version_number INT NOT NULL,
  active BOOLEAN DEFAULT TRUE,
  
  -- Scope
  actor_type TEXT,  -- Optional filter: applies only to this actor type
  protected_action_id UUID REFERENCES protected_actions(action_id),
  
  -- Conditions
  conditions JSONB,  -- Extensible condition object
  
  -- Effect
  effect TEXT NOT NULL,  -- ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
  constraints JSONB,  -- Constraints if ALLOW_WITH_CONSTRAINTS
  
  -- Approval
  approval_required BOOLEAN DEFAULT FALSE,
  required_approval_count INT DEFAULT 1,
  required_approver_types TEXT[],  -- Array of actor types authorized to approve
  approval_expiry_seconds INT,
  
  -- Precedence
  precedence INT DEFAULT 100,  -- Lower number = higher precedence
  
  -- Validity
  effective_from TIMESTAMPTZ DEFAULT NOW(),
  effective_until TIMESTAMPTZ,
  
  -- Provenance
  created_by_actor_id UUID REFERENCES governance_actors(actor_id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  reason_for_creation TEXT,
  
  CONSTRAINT valid_effect CHECK (effect IN ('ALLOW', 'ALLOW_WITH_CONSTRAINTS', 'REQUIRE_APPROVAL', 'DENY')),
  UNIQUE(policy_version_number, policy_id)
);

CREATE INDEX idx_policies_active ON governance_policies(active) WHERE active = TRUE;
CREATE INDEX idx_policies_action ON governance_policies(protected_action_id) WHERE active = TRUE;
CREATE INDEX idx_policies_actor ON governance_policies(actor_type) WHERE active = TRUE;
CREATE INDEX idx_policies_precedence ON governance_policies(precedence ASC);
CREATE INDEX idx_policies_validity ON governance_policies(effective_from, effective_until) WHERE active = TRUE;

-- ============================================================================
-- 4. AUTHORITY (Who can do what)
-- ============================================================================

CREATE TABLE governance_authority (
  authority_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Subject and action
  actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  protected_action_id UUID NOT NULL REFERENCES protected_actions(action_id),
  
  -- Scope
  resource_scope TEXT,  -- e.g., 'all', 'task:specific-id', 'node:specific-id', 'domain:analysis'
  
  -- Status
  state TEXT DEFAULT 'active',  -- active, revoked, expired, suspended
  
  -- Constraints
  constraints JSONB,  -- Enforceable limits (max_attempts, duration, read_only, etc.)
  
  -- Delegation
  can_delegate BOOLEAN DEFAULT FALSE,
  delegated_from_authority_id UUID REFERENCES governance_authority(authority_id),
  
  -- Validity
  granted_at TIMESTAMPTZ DEFAULT NOW(),
  granted_by_actor_id UUID REFERENCES governance_actors(actor_id),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  
  reason_for_grant TEXT,
  reason_for_revocation TEXT,
  
  CONSTRAINT valid_state CHECK (state IN ('active', 'revoked', 'expired', 'suspended')),
  CONSTRAINT valid_grant CHECK (granted_at <= NOW())
);

CREATE INDEX idx_authority_actor ON governance_authority(actor_id, state);
CREATE INDEX idx_authority_action ON governance_authority(protected_action_id);
CREATE INDEX idx_authority_scope ON governance_authority(resource_scope);
CREATE INDEX idx_authority_state ON governance_authority(state);
CREATE INDEX idx_authority_expires ON governance_authority(expires_at) WHERE state = 'active';

-- ============================================================================
-- 5. DELEGATION (Authority delegation chain)
-- ============================================================================

CREATE TABLE governance_delegation (
  delegation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Grantor/recipient
  grantor_actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  recipient_actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  
  -- What is delegated
  protected_action_id UUID NOT NULL REFERENCES protected_actions(action_id),
  
  -- Scope
  resource_scope TEXT,  -- Must be subset of grantor's authority scope
  
  -- Constraints
  constraints JSONB,  -- Must be subset of grantor's constraints
  
  -- Status
  state TEXT DEFAULT 'active',  -- active, revoked, expired, suspended
  
  -- Validity
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  
  reason TEXT,
  
  CONSTRAINT valid_state CHECK (state IN ('active', 'revoked', 'expired', 'suspended')),
  CONSTRAINT grantor_not_recipient CHECK (grantor_actor_id != recipient_actor_id)
);

CREATE INDEX idx_delegation_grantor ON governance_delegation(grantor_actor_id, state);
CREATE INDEX idx_delegation_recipient ON governance_delegation(recipient_actor_id, state);
CREATE INDEX idx_delegation_action ON governance_delegation(protected_action_id);

-- ============================================================================
-- 6. GOVERNANCE DECISIONS (Every decision is recorded)
-- ============================================================================

CREATE TABLE governance_decisions (
  decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Action being evaluated
  protected_action_id UUID NOT NULL REFERENCES protected_actions(action_id),
  actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  
  -- Request details
  resource_type TEXT,  -- task, strategy, experiment, node, structure, etc.
  resource_id UUID,
  scope_context JSONB,  -- Task context, constraints, etc.
  
  -- Policies evaluated
  policies_evaluated UUID[],  -- Array of policy IDs that were evaluated
  conflict_count INT DEFAULT 0,  -- Number of conflicting policies
  
  -- Constraints
  applied_constraints JSONB,  -- Constraints that will be enforced
  
  -- Decision
  effect TEXT NOT NULL,  -- ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
  reasoning TEXT,
  confidence_score FLOAT DEFAULT 1.0,  -- 1.0 = certain, <1.0 = some uncertainty
  
  -- Governance status
  governance_success BOOLEAN DEFAULT TRUE,  -- FALSE if governance evaluation itself failed
  governance_error TEXT,
  
  -- Authority status
  authority_found BOOLEAN DEFAULT FALSE,
  authority_sufficient BOOLEAN DEFAULT FALSE,
  
  -- Approval status (if required)
  approval_required BOOLEAN DEFAULT FALSE,
  approval_request_id UUID,  -- Reference to approval request
  
  -- Timestamps
  evaluated_at TIMESTAMPTZ DEFAULT NOW(),
  policy_version_at_eval TIMESTAMPTZ,  -- Policy version active at decision time
  
  CONSTRAINT valid_effect CHECK (effect IN ('ALLOW', 'ALLOW_WITH_CONSTRAINTS', 'REQUIRE_APPROVAL', 'DENY'))
);

CREATE INDEX idx_decisions_action ON governance_decisions(protected_action_id);
CREATE INDEX idx_decisions_actor ON governance_decisions(actor_id);
CREATE INDEX idx_decisions_effect ON governance_decisions(effect);
CREATE INDEX idx_decisions_time ON governance_decisions(evaluated_at DESC);
CREATE INDEX idx_decisions_resource ON governance_decisions(resource_type, resource_id);

-- ============================================================================
-- 7. APPROVAL REQUESTS & WORKFLOW
-- ============================================================================

CREATE TABLE governance_approval_requests (
  approval_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Decision being approved
  decision_id UUID NOT NULL REFERENCES governance_decisions(decision_id),
  
  -- Action details
  protected_action_id UUID NOT NULL REFERENCES protected_actions(action_id),
  actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  resource_type TEXT,
  resource_id UUID,
  
  -- Approval details
  reason_for_approval_requirement TEXT,
  required_approval_count INT DEFAULT 1,
  required_approver_types TEXT[],
  
  -- Status
  status TEXT DEFAULT 'pending',  -- pending, approved, denied, expired, cancelled
  approval_count INT DEFAULT 0,
  denial_count INT DEFAULT 0,
  
  -- Expiry
  requested_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  decision_enforced_at TIMESTAMPTZ,  -- When approved decision was executed
  
  CONSTRAINT valid_status CHECK (status IN ('pending', 'approved', 'denied', 'expired', 'cancelled'))
);

CREATE INDEX idx_approvals_status ON governance_approval_requests(status) WHERE status IN ('pending', 'approved');
CREATE INDEX idx_approvals_actor ON governance_approval_requests(actor_id);
CREATE INDEX idx_approvals_expires ON governance_approval_requests(expires_at) WHERE status = 'pending';

-- Approval decisions (who approved/denied and when)
CREATE TABLE governance_approval_decisions (
  approval_decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  approval_request_id UUID NOT NULL REFERENCES governance_approval_requests(approval_request_id),
  
  approver_actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  decision TEXT NOT NULL,  -- approved, denied
  reason TEXT,
  
  decided_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT valid_decision CHECK (decision IN ('approved', 'denied'))
);

CREATE INDEX idx_approval_decisions_request ON governance_approval_decisions(approval_request_id);
CREATE INDEX idx_approval_decisions_approver ON governance_approval_decisions(approver_actor_id);

-- ============================================================================
-- 8. EMERGENCY RESTRICTIONS
-- ============================================================================

CREATE TABLE governance_emergency_restrictions (
  restriction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  name TEXT NOT NULL,
  description TEXT,
  
  -- Scope
  restricted_action_codes TEXT[],  -- Actions to restrict (e.g., ['experiment_creation', 'node_provisioning_request'])
  restricted_actor_types TEXT[],  -- Actor types affected (e.g., ['ai_node', 'automated_process'])
  
  -- Status
  state TEXT DEFAULT 'active',  -- active, revoked, expired
  
  -- Authority
  created_by_actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  revoked_by_actor_id UUID REFERENCES governance_actors(actor_id),
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  
  reason TEXT,
  
  CONSTRAINT valid_state CHECK (state IN ('active', 'revoked', 'expired'))
);

CREATE INDEX idx_emergency_restrictions_state ON governance_emergency_restrictions(state) WHERE state = 'active';
CREATE INDEX idx_emergency_restrictions_actions ON governance_emergency_restrictions USING GIN (restricted_action_codes) WHERE state = 'active';

-- ============================================================================
-- 9. AUTONOMY CONFIGURATION
-- ============================================================================

CREATE TABLE governance_autonomy_modes (
  autonomy_mode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  mode_name TEXT NOT NULL,
  description TEXT,
  
  -- Mode levels
  allow_proposal_generation BOOLEAN DEFAULT TRUE,
  allow_autonomous_execution BOOLEAN DEFAULT FALSE,
  allow_experiment_creation BOOLEAN DEFAULT FALSE,
  allow_promotion BOOLEAN DEFAULT FALSE,
  allow_node_evolution BOOLEAN DEFAULT FALSE,
  allow_self_organisation BOOLEAN DEFAULT FALSE,
  allow_external_tools BOOLEAN DEFAULT FALSE,
  
  -- Scope
  applicable_actor_types TEXT[],
  applicable_protected_actions TEXT[],
  
  -- Status
  active BOOLEAN DEFAULT TRUE,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  created_by_actor_id UUID REFERENCES governance_actors(actor_id),
  
  UNIQUE(mode_name)
);

INSERT INTO governance_autonomy_modes (mode_name, description, allow_proposal_generation, allow_autonomous_execution, applicable_actor_types) VALUES
  ('observe_only', 'Observe and report only; no execution', FALSE, FALSE, ARRAY['ai_node', 'automated_process']),
  ('propose_only', 'Generate proposals; require approval for execution', TRUE, FALSE, ARRAY['ai_node', 'automated_process']),
  ('low_risk_autonomous', 'Autonomous execution for low-risk actions only', TRUE, TRUE, ARRAY['ai_node']),
  ('bounded_experimentation', 'Can create experiments within resource bounds', TRUE, TRUE, ARRAY['ai_node', 'automated_process']);

CREATE INDEX idx_autonomy_modes_active ON governance_autonomy_modes(active);

-- ============================================================================
-- 10. TOOL AUTHORITY (Separate from capability)
-- ============================================================================

CREATE TABLE governance_tool_authority (
  tool_authority_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  actor_id UUID NOT NULL REFERENCES governance_actors(actor_id),
  
  tool_name TEXT NOT NULL,  -- git_read, git_write, vps_read, vps_execute, db_read, db_write, web_research, external_communication, etc.
  
  state TEXT DEFAULT 'active',  -- active, revoked, restricted, suspended
  
  -- Constraints
  constraints JSONB,  -- Read-only, specific resources, rate limits, etc.
  
  -- Validity
  granted_at TIMESTAMPTZ DEFAULT NOW(),
  granted_by_actor_id UUID REFERENCES governance_actors(actor_id),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  
  reason_for_grant TEXT,
  reason_for_revocation TEXT,
  
  CONSTRAINT valid_state CHECK (state IN ('active', 'revoked', 'restricted', 'suspended')),
  UNIQUE(actor_id, tool_name)
);

CREATE INDEX idx_tool_authority_actor ON governance_tool_authority(actor_id, state);
CREATE INDEX idx_tool_authority_tool ON governance_tool_authority(tool_name);

-- ============================================================================
-- 11. CONSTRAINT DEFINITIONS
-- ============================================================================

CREATE TABLE governance_constraint_types (
  constraint_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  constraint_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  
  -- Enforcement
  enforceable BOOLEAN DEFAULT TRUE,
  enforcement_mechanism TEXT,  -- code_check, resource_limit, rate_limit, scope_filter, timeout, etc.
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO governance_constraint_types (constraint_code, name, description, enforceable, enforcement_mechanism) VALUES
  ('permitted_tools', 'Permitted Tools', 'Restrict to specific tools', TRUE, 'code_check'),
  ('permitted_task_scope', 'Permitted Task Scope', 'Restrict to specific task types/domains', TRUE, 'code_check'),
  ('max_resource_utilisation', 'Max Resource Utilisation', 'Limit resource consumption', TRUE, 'resource_limit'),
  ('max_team_size', 'Max Team Size', 'Limit organisational structure size', TRUE, 'code_check'),
  ('max_duration_seconds', 'Max Duration', 'Limit execution duration', TRUE, 'timeout'),
  ('read_only', 'Read-Only Mode', 'Prevent data mutations', TRUE, 'code_check'),
  ('no_external_side_effects', 'No External Side Effects', 'Block external communication', TRUE, 'code_check'),
  ('node_definition_locked', 'Node Definition Locked', 'Prevent node definition changes', TRUE, 'code_check'),
  ('no_provisioning', 'No Provisioning', 'Block new infrastructure requests', TRUE, 'code_check'),
  ('experimental_only', 'Experimental Only', 'Limit to experimental/test resources', TRUE, 'scope_filter'),
  ('requires_human_approval', 'Requires Human Approval', 'Escalate to human authority', TRUE, 'code_check'),
  ('rate_limit', 'Rate Limit', 'Limit action frequency', TRUE, 'rate_limit')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 12. GOVERNANCE AUDIT LOG (All decisions and changes)
-- ============================================================================

CREATE TABLE governance_audit_log (
  audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Event
  event_type TEXT NOT NULL,  -- governance_evaluated, allow, constrained_allow, approval_requested, approved, denied, revoked, action_blocked, authority_granted, authority_revoked, policy_created, policy_modified, policy_disabled, constraint_violated, emergency_restriction, exception_granted, delegation_created, delegation_revoked
  
  -- What happened
  decision_id UUID REFERENCES governance_decisions(decision_id),
  approval_request_id UUID REFERENCES governance_approval_requests(approval_request_id),
  authority_id UUID REFERENCES governance_authority(authority_id),
  policy_id UUID REFERENCES governance_policies(policy_id),
  
  -- Who and what
  actor_id UUID REFERENCES governance_actors(actor_id),
  protected_action_id UUID REFERENCES protected_actions(action_id),
  
  resource_type TEXT,
  resource_id UUID,
  
  -- Details
  details JSONB,
  
  recorded_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT valid_event_type CHECK (event_type IN (
    'governance_evaluated', 'allow', 'constrained_allow', 'approval_requested', 'approved', 'denied', 'revoked',
    'action_blocked', 'authority_granted', 'authority_revoked', 'policy_created', 'policy_modified', 'policy_disabled',
    'constraint_violated', 'emergency_restriction', 'exception_granted', 'delegation_created', 'delegation_revoked'
  ))
);

CREATE INDEX idx_audit_event ON governance_audit_log(event_type);
CREATE INDEX idx_audit_actor ON governance_audit_log(actor_id);
CREATE INDEX idx_audit_time ON governance_audit_log(recorded_at DESC);
CREATE INDEX idx_audit_decision ON governance_audit_log(decision_id);

-- ============================================================================
-- 13. GOVERNANCE HEALTH & STATUS
-- ============================================================================

CREATE TABLE governance_system_status (
  status_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Health checks
  governance_operational BOOLEAN DEFAULT TRUE,
  last_health_check_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Active policy/rule version
  active_policy_version INT,
  
  -- Restrictions
  active_emergency_restrictions INT DEFAULT 0,
  
  -- Pending approvals
  pending_approvals_count INT DEFAULT 0,
  
  -- Status
  details JSONB,
  
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- END OF MIGRATION 020
-- ============================================================================
