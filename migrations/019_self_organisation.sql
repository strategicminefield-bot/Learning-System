-- SECTION 19: SELF-ORGANISATION LAYER
-- Organisational structure definition, versioning, role assignment, team formation, and evidence-driven evolution

-- ============================================================================
-- 1. ORGANISATIONAL STRUCTURE DEFINITIONS
-- ============================================================================

CREATE TABLE organisational_structures (
  structure_id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  structure_type TEXT NOT NULL,  -- single_node, planner_executor, architect_builder_verifier, parallel_workers, etc.
  purpose TEXT,
  description TEXT,
  applicability_scope JSONB,  -- {"task_types": ["type1", "type2"], "domains": [...]}
  required_capabilities JSONB,  -- {"roles": {"architect": ["planning"], "executor": ["execution"]}}
  coordination_pattern TEXT,  -- sequential, parallel, hierarchical, peer, etc.
  task_workflow_constraints JSONB,  -- Entry/exit conditions, ordering constraints
  fallback_structure_id UUID REFERENCES organisational_structures(structure_id),
  lifecycle_state TEXT NOT NULL DEFAULT 'candidate',  -- candidate, experimental, validated, active, restricted, disputed, superseded, retired
  provenance JSONB,  -- {"created_from": "structure_id", "triggered_by": "proposal_id"}
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by TEXT,  -- Node/agent identifier
  CONSTRAINT valid_lifecycle CHECK (lifecycle_state IN ('candidate', 'experimental', 'validated', 'active', 'restricted', 'disputed', 'superseded', 'retired')),
  CONSTRAINT no_self_fallback CHECK (fallback_structure_id IS NULL OR fallback_structure_id <> structure_id)
);

CREATE INDEX idx_org_structures_type ON organisational_structures(structure_type);
CREATE INDEX idx_org_structures_state ON organisational_structures(lifecycle_state);
CREATE INDEX idx_org_structures_applicability ON organisational_structures USING GIN(applicability_scope);
CREATE INDEX idx_org_structures_created ON organisational_structures(created_at DESC);

-- ============================================================================
-- 2. STRUCTURE VERSIONING
-- ============================================================================

CREATE TABLE organisational_structure_versions (
  version_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  version_number INT NOT NULL,
  parent_version_id UUID REFERENCES organisational_structure_versions(version_id),
  
  -- Immutable snapshot
  name TEXT NOT NULL,
  structure_type TEXT NOT NULL,
  purpose TEXT,
  coordination_pattern TEXT,
  required_capabilities JSONB,
  task_workflow_constraints JSONB,
  
  -- Lineage and decision tracking
  derived_from_structure_id UUID REFERENCES organisational_structures(structure_id),
  version_change_type TEXT,  -- new, refinement, specialisation, generalisation, supersession
  change_rationale TEXT,
  triggered_by_proposal_id UUID,
  triggered_by_evidence JSONB,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(structure_id, version_number)
);

CREATE INDEX idx_org_versions_structure ON organisational_structure_versions(structure_id);
CREATE INDEX idx_org_versions_parent ON organisational_structure_versions(parent_version_id);
CREATE INDEX idx_org_versions_created ON organisational_structure_versions(created_at DESC);

-- ============================================================================
-- 3. ORGANISATIONAL ROLES
-- ============================================================================

CREATE TABLE organisational_roles (
  role_id UUID PRIMARY KEY,
  role_name TEXT NOT NULL UNIQUE,  -- architect, executor, verifier, planner, coordinator, reviewer, etc.
  description TEXT,
  required_capabilities TEXT[],  -- Array of required capabilities
  required_attributes JSONB,  -- {"independence": true, "can_escalate": false}
  responsibility_scope JSONB,  -- What this role is responsible for
  authority_scope JSONB,  -- What authority this role has (nil for most roles)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_roles_name ON organisational_roles(role_name);

-- ============================================================================
-- 4. STRUCTURE ROLES (Mapping roles to structures)
-- ============================================================================

CREATE TABLE structure_roles (
  structure_role_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  sequence_number INT NOT NULL,  -- Order in structure
  required_capability_subset TEXT[],  -- Specific required capabilities for this role in this structure
  capacity INT DEFAULT 1,  -- Number of nodes that can fill this role
  optional BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(structure_id, role_id)
);

CREATE INDEX idx_struct_roles_structure ON structure_roles(structure_id);
CREATE INDEX idx_struct_roles_role ON structure_roles(role_id);

-- ============================================================================
-- 5. STRUCTURE RELATIONSHIPS (Coordination between roles/nodes)
-- ============================================================================

CREATE TABLE structure_relationships (
  relationship_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  source_role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  target_role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  relationship_type TEXT NOT NULL,  -- delegates_to, reports_to, verifies, reviews, supplies_context_to, repairs_after, collaborates_with, coordinates
  cardinality TEXT,  -- one_to_one, one_to_many, many_to_one, many_to_many
  handoff_required BOOLEAN DEFAULT FALSE,
  context_required JSONB,  -- Context to be passed
  verification_required BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_relationship CHECK (relationship_type IN (
    'delegates_to', 'reports_to', 'verifies', 'reviews', 'supplies_context_to', 
    'repairs_after', 'collaborates_with', 'coordinates'
  ))
);

CREATE INDEX idx_struct_rels_structure ON structure_relationships(structure_id);
CREATE INDEX idx_struct_rels_source ON structure_relationships(source_role_id);
CREATE INDEX idx_struct_rels_target ON structure_relationships(target_role_id);

-- ============================================================================
-- 6. TEAM INSTANTIATIONS (Actual team/group for a work item)
-- ============================================================================

CREATE TABLE team_instantiations (
  team_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  structure_version_id UUID REFERENCES organisational_structure_versions(version_id),
  task_id UUID REFERENCES tasks(task_id),
  
  -- Binding to work
  workflow_id UUID,
  assignment_id UUID,
  
  -- Team lifecycle
  team_type TEXT NOT NULL,  -- persistent, temporary
  team_status TEXT NOT NULL DEFAULT 'forming',  -- forming, active, completed, dissolved, failed
  
  -- Bounds for temporary teams
  expected_duration_seconds INT,
  start_time TIMESTAMPTZ DEFAULT NOW(),
  end_time TIMESTAMPTZ,
  
  -- Execution context
  execution_plan_id UUID,
  parent_team_id UUID REFERENCES team_instantiations(team_id),
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  created_by TEXT,
  CONSTRAINT valid_team_status CHECK (team_status IN ('forming', 'active', 'completed', 'dissolved', 'failed')),
  CONSTRAINT valid_team_type CHECK (team_type IN ('persistent', 'temporary'))
);

CREATE INDEX idx_teams_structure ON team_instantiations(structure_id);
CREATE INDEX idx_teams_task ON team_instantiations(task_id);
CREATE INDEX idx_teams_status ON team_instantiations(team_status);
CREATE INDEX idx_teams_created ON team_instantiations(created_at DESC);
CREATE INDEX idx_teams_parent ON team_instantiations(parent_team_id);

-- ============================================================================
-- 7. TEAM MEMBERSHIPS (Members and their roles in a team)
-- ============================================================================

CREATE TABLE team_memberships (
  membership_id UUID PRIMARY KEY,
  team_id UUID NOT NULL REFERENCES team_instantiations(team_id),
  node_definition_id UUID NOT NULL REFERENCES node_definitions(definition_id),
  node_instance_id UUID REFERENCES node_instances(instance_id),
  role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  
  -- Binding to assignments
  assignment_id UUID,
  
  -- Membership status
  membership_status TEXT NOT NULL DEFAULT 'assigned',  -- assigned, active, completed, failed, replaced
  
  -- Why this node was selected
  selection_rationale JSONB,
  eligibility_score FLOAT DEFAULT 0,
  
  -- Replacement tracking
  replaced_by_membership_id UUID REFERENCES team_memberships(membership_id),
  replacement_reason TEXT,
  replacement_time TIMESTAMPTZ,
  
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  left_at TIMESTAMPTZ,
  CONSTRAINT valid_membership_status CHECK (membership_status IN ('assigned', 'active', 'completed', 'failed', 'replaced'))
);

CREATE INDEX idx_memberships_team ON team_memberships(team_id);
CREATE INDEX idx_memberships_node_def ON team_memberships(node_definition_id);
CREATE INDEX idx_memberships_node_inst ON team_memberships(node_instance_id);
CREATE INDEX idx_memberships_role ON team_memberships(role_id);
CREATE INDEX idx_memberships_status ON team_memberships(membership_status);

-- ============================================================================
-- 8. EXECUTION PLANS (Structured work plans for team execution)
-- ============================================================================

CREATE TABLE execution_plans (
  plan_id UUID PRIMARY KEY,
  team_id UUID NOT NULL REFERENCES team_instantiations(team_id),
  task_id UUID REFERENCES tasks(task_id),
  
  -- Objective and strategy
  objective TEXT NOT NULL,
  selected_structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  selected_version_id UUID REFERENCES organisational_structure_versions(version_id),
  
  -- Members and roles
  members JSONB NOT NULL,  -- [{"role": "architect", "node": "...", "capability": "..."}]
  
  -- Workflow specification
  steps JSONB NOT NULL,  -- Ordered execution steps with constraints
  coordination_directives JSONB,  -- How team coordinates
  handoff_conditions JSONB,  -- When handoffs occur
  
  -- Constraints and constraints
  task_constraints JSONB,
  resource_constraints JSONB,
  time_constraints JSONB,
  
  -- Fallback and contingency
  fallback_structure_id UUID REFERENCES organisational_structures(structure_id),
  fallback_conditions JSONB,
  replan_triggers JSONB,
  
  -- Verification and accountability
  verification_roles TEXT[],  -- Which roles must verify
  accountability_assignments JSONB,
  
  -- Status
  plan_status TEXT NOT NULL DEFAULT 'created',  -- created, approved, executing, paused, completed, failed, replanned
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_plan_status CHECK (plan_status IN ('created', 'approved', 'executing', 'paused', 'completed', 'failed', 'replanned'))
);

CREATE INDEX idx_plans_team ON execution_plans(team_id);
CREATE INDEX idx_plans_task ON execution_plans(task_id);
CREATE INDEX idx_plans_status ON execution_plans(plan_status);

-- ============================================================================
-- 9. HANDOFFS (Work transfers between roles/team members)
-- ============================================================================

CREATE TABLE team_handoffs (
  handoff_id UUID PRIMARY KEY,
  team_id UUID NOT NULL REFERENCES team_instantiations(team_id),
  execution_plan_id UUID REFERENCES execution_plans(plan_id),
  
  -- Source and destination
  source_role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  target_role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  source_membership_id UUID REFERENCES team_memberships(membership_id),
  target_membership_id UUID REFERENCES team_memberships(membership_id),
  
  -- Work being handed off
  artifact_description TEXT,
  artifact_data JSONB,
  context_supplied JSONB,
  
  -- Handoff status and evidence
  handoff_type TEXT,  -- result, verification, context, repair, etc.
  handoff_status TEXT NOT NULL DEFAULT 'pending',  -- pending, acknowledged, accepted, failed
  reason TEXT,
  
  attempted_at TIMESTAMPTZ DEFAULT NOW(),
  acknowledged_at TIMESTAMPTZ,
  accepted_at TIMESTAMPTZ,
  failed_at TIMESTAMPTZ,
  CONSTRAINT valid_handoff_status CHECK (handoff_status IN ('pending', 'acknowledged', 'accepted', 'failed'))
);

CREATE INDEX idx_handoffs_team ON team_handoffs(team_id);
CREATE INDEX idx_handoffs_plan ON team_handoffs(execution_plan_id);
CREATE INDEX idx_handoffs_status ON team_handoffs(handoff_status);

-- ============================================================================
-- 10. ORGANISATIONAL EVIDENCE (Structure effectiveness evidence)
-- ============================================================================

CREATE TABLE organisational_evidence (
  evidence_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  team_id UUID REFERENCES team_instantiations(team_id),
  task_id UUID REFERENCES tasks(task_id),
  
  -- Evidence type and context
  evidence_type TEXT NOT NULL,  -- verified_completion, failure, repair, capability_gap, coordination_failure, handoff_failure, verifier_disagreement, execution_time, cost, quality_metric
  applicable_context JSONB,  -- {"task_types": [...], "domains": [...], "scales": [...]}
  
  -- Evidence content
  outcome_status TEXT,  -- success, failure, partial, repairs_needed
  quality_assessment FLOAT,
  execution_time_seconds INT,
  repair_frequency INT,
  failure_attribution JSONB,  -- {"cause": "node_failure|strategy|capability_gap|handoff|coordination|structure_design|insufficient_evidence", "detail": "..."}
  
  -- Confidence
  observation_confidence FLOAT DEFAULT 1.0,  -- 0-1
  observation_count INT DEFAULT 1,
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_org_evidence_structure ON organisational_evidence(structure_id);
CREATE INDEX idx_org_evidence_type ON organisational_evidence(evidence_type);
CREATE INDEX idx_org_evidence_context ON organisational_evidence USING GIN(applicable_context);

-- ============================================================================
-- 11. ORGANISATIONAL LEARNING FEEDBACK (Evidence for future structure selection)
-- ============================================================================

CREATE TABLE organisational_learning (
  learning_id UUID PRIMARY KEY,
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  
  -- Evidence aggregation
  evidence_type TEXT NOT NULL,  -- what_works, what_fails, gap, opportunity, constraint
  applicable_context JSONB,
  
  -- Learning content
  insight TEXT,
  supporting_evidence_ids UUID[],
  evidence_count INT,
  success_rate FLOAT,
  reliability_score FLOAT,  -- based on evidence diversity and quantity
  
  -- When discovered
  discovered_at TIMESTAMPTZ DEFAULT NOW(),
  
  -- Potential actions
  recommended_actions JSONB
);

CREATE INDEX idx_org_learning_structure ON organisational_learning(structure_id);
CREATE INDEX idx_org_learning_type ON organisational_learning(evidence_type);

-- ============================================================================
-- 12. ORGANISATIONAL PROPOSALS (Change proposals for structures)
-- ============================================================================

CREATE TABLE organisational_proposals (
  proposal_id UUID PRIMARY KEY,
  proposal_type TEXT NOT NULL,  -- role_addition, role_removal, member_replacement, topology_change, specialisation, simplification, expansion, split, merge, supersession, retirement
  
  -- What it's about
  target_structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  target_version_id UUID REFERENCES organisational_structure_versions(version_id),
  
  -- Triggering evidence
  triggering_evidence_ids UUID[] DEFAULT ARRAY[]::UUID[],
  trigger_type TEXT,  -- repeated_coordination_failure, repeated_missing_capability, repeated_verifier_disagreement, repeated_repair_bottleneck, repeated_success_pattern, new_capability, changing_demand, underperformance, experimental_alternative
  trigger_count INT,
  
  -- Proposed change
  proposed_change JSONB NOT NULL,  -- Structure of proposed change
  expected_benefit TEXT,
  expected_cost JSONB,  -- Resource/time/complexity cost
  
  -- Status
  proposal_status TEXT NOT NULL DEFAULT 'proposed',  -- proposed, evaluated, accepted, rejected, implemented, superseded
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  evaluated_at TIMESTAMPTZ,
  CONSTRAINT valid_proposal_type CHECK (proposal_type IN (
    'role_addition', 'role_removal', 'member_replacement', 'topology_change', 'specialisation', 
    'simplification', 'expansion', 'split', 'merge', 'supersession', 'retirement'
  ))
);

CREATE INDEX idx_org_proposals_target ON organisational_proposals(target_structure_id);
CREATE INDEX idx_org_proposals_type ON organisational_proposals(proposal_type);
CREATE INDEX idx_org_proposals_status ON organisational_proposals(proposal_status);
CREATE INDEX idx_org_proposals_trigger ON organisational_proposals(trigger_type);

-- ============================================================================
-- 13. ORGANISATIONAL DECISIONS (What structure was chosen and why)
-- ============================================================================

CREATE TABLE organisational_decisions (
  decision_id UUID PRIMARY KEY,
  
  -- Context
  task_id UUID REFERENCES tasks(task_id),
  workflow_id UUID,
  
  -- What was needed
  work_objective TEXT,
  capability_requirements JSONB,
  role_requirements TEXT[],
  
  -- Candidates considered
  candidate_structure_ids UUID[] NOT NULL,
  
  -- Evidence used
  supporting_evidence_ids UUID[] DEFAULT ARRAY[]::UUID[],
  contradictory_evidence_ids UUID[] DEFAULT ARRAY[]::UUID[],
  
  -- Decision
  selected_structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  selected_version_id UUID REFERENCES organisational_structure_versions(version_id),
  rejected_candidates JSONB,  -- {"structure_id": "reason_rejected"}
  
  -- Constraints applied
  applied_constraints JSONB,
  constraint_overrides JSONB,  -- {"explicit_task_constraint": "why overridden"}
  
  -- Decision rationale
  decision_rationale TEXT,
  evidence_sufficiency TEXT,  -- sufficient, adequate, low, insufficient
  contradictions_present BOOLEAN DEFAULT FALSE,
  decision_confidence FLOAT DEFAULT 0.5,
  
  -- Fallback/contingency
  fallback_structure_id UUID REFERENCES organisational_structures(structure_id),
  contingency_conditions JSONB,
  
  -- Execution connection
  team_id UUID REFERENCES team_instantiations(team_id),
  execution_plan_id UUID REFERENCES execution_plans(plan_id),
  
  -- Authority and control
  rule_config_version_id UUID,  -- Which version of org rules applied
  autonomous_decision BOOLEAN DEFAULT FALSE,
  decision_authority TEXT,  -- Who/what made decision
  approval_required BOOLEAN DEFAULT FALSE,
  
  decision_status TEXT NOT NULL DEFAULT 'made',  -- made, approved, rejected, executing, completed, failed, superseded
  
  made_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT valid_decision_status CHECK (decision_status IN ('made', 'approved', 'rejected', 'executing', 'completed', 'failed', 'superseded'))
);

CREATE INDEX idx_org_decisions_task ON organisational_decisions(task_id);
CREATE INDEX idx_org_decisions_selected ON organisational_decisions(selected_structure_id);
CREATE INDEX idx_org_decisions_team ON organisational_decisions(team_id);
CREATE INDEX idx_org_decisions_status ON organisational_decisions(decision_status);
CREATE INDEX idx_org_decisions_confidence ON organisational_decisions(decision_confidence DESC);

-- ============================================================================
-- 14. ORGANISATIONAL RULE CONFIGURATION (Bounds and controls for self-organisation)
-- ============================================================================

CREATE TABLE organisational_rule_configs (
  config_version_id UUID PRIMARY KEY,
  config_version_number INT NOT NULL UNIQUE,
  
  -- Controls
  max_team_size INT DEFAULT 10,
  max_hierarchy_depth INT DEFAULT 3,
  max_active_temporary_teams INT DEFAULT 20,
  max_reorganisations_per_task INT DEFAULT 3,
  max_candidate_generation_per_decision INT DEFAULT 10,
  reorganisation_cooldown_seconds INT DEFAULT 300,  -- Minimum time between reorganisations
  
  -- Autonomous control
  allow_autonomous_organisation BOOLEAN DEFAULT FALSE,  -- When FALSE, proposals may be created but not applied without authority
  allow_autonomous_team_formation BOOLEAN DEFAULT FALSE,
  allow_autonomous_member_replacement BOOLEAN DEFAULT FALSE,
  allow_autonomous_reorganisation BOOLEAN DEFAULT FALSE,
  
  -- Evidence requirements
  min_evidence_for_promotion FLOAT DEFAULT 0.7,  -- Confidence threshold
  experiment_required_for_new_structures BOOLEAN DEFAULT TRUE,
  validation_required_for_new_structures BOOLEAN DEFAULT TRUE,
  
  -- Authority boundaries
  require_approval_for_team_formation BOOLEAN DEFAULT FALSE,
  require_approval_for_reorganisation BOOLEAN DEFAULT FALSE,
  
  -- Task/context constraints
  override_explicit_constraints BOOLEAN DEFAULT FALSE,  -- Can org learning override explicit task constraints?
  respect_node_availability BOOLEAN DEFAULT TRUE,
  respect_node_health_status BOOLEAN DEFAULT TRUE,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  activated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_org_rules_version ON organisational_rule_configs(config_version_number DESC);

-- ============================================================================
-- 15. ORGANISATIONAL HISTORY (Audit trail for structure lifecycle)
-- ============================================================================

CREATE TABLE organisational_history (
  history_id UUID PRIMARY KEY,
  
  -- Entity
  structure_id UUID REFERENCES organisational_structures(structure_id),
  team_id UUID REFERENCES team_instantiations(team_id),
  
  -- Event
  event_type TEXT NOT NULL,  -- structure_created, structure_versioned, team_instantiated, member_joined, member_replaced, member_left, handoff_completed, reorganisation_proposed, reorganisation_applied, structure_promoted, structure_restricted, structure_superseded, structure_retired, team_dissolved, temporary_team_expired
  
  new_state TEXT,
  previous_state TEXT,
  
  -- Decision context
  decision_id UUID REFERENCES organisational_decisions(decision_id),
  proposal_id UUID REFERENCES organisational_proposals(proposal_id),
  
  event_metadata JSONB,
  recorded_by TEXT,
  
  recorded_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_history_event CHECK (event_type IN (
    'structure_created', 'structure_versioned', 'team_instantiated', 'member_joined', 'member_replaced', 'member_left',
    'handoff_completed', 'reorganisation_proposed', 'reorganisation_applied', 'structure_promoted', 'structure_restricted',
    'structure_superseded', 'structure_retired', 'team_dissolved', 'temporary_team_expired'
  ))
);

CREATE INDEX idx_org_history_structure ON organisational_history(structure_id);
CREATE INDEX idx_org_history_team ON organisational_history(team_id);
CREATE INDEX idx_org_history_event ON organisational_history(event_type);
CREATE INDEX idx_org_history_time ON organisational_history(recorded_at DESC);

-- ============================================================================
-- 16. ORGANISATIONAL LINEAGE (Structural relationships and evolution)
-- ============================================================================

CREATE TABLE organisational_lineage (
  lineage_id UUID PRIMARY KEY,
  
  child_structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  parent_structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  
  relationship_type TEXT NOT NULL,  -- derived_from, revises, specialises, generalises, supersedes, replaces, split_from, merged_from
  
  reason TEXT,
  evidence_ids UUID[],
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  
  CONSTRAINT valid_lineage_type CHECK (relationship_type IN (
    'derived_from', 'revises', 'specialises', 'generalises', 'supersedes', 'replaces', 'split_from', 'merged_from'
  ))
);

CREATE INDEX idx_org_lineage_child ON organisational_lineage(child_structure_id);
CREATE INDEX idx_org_lineage_parent ON organisational_lineage(parent_structure_id);

-- ============================================================================
-- 17. REORGANISATION TRACKING (Bounds on structure changes during active work)
-- ============================================================================

CREATE TABLE reorganisation_tracking (
  tracking_id UUID PRIMARY KEY,
  
  team_id UUID NOT NULL REFERENCES team_instantiations(team_id),
  task_id UUID REFERENCES tasks(task_id),
  
  -- Reorganisations performed
  reorganisation_count INT DEFAULT 0,
  reorganisation_history JSONB,  -- [{time: "...", trigger: "...", change: "..."}]
  
  -- Bounds
  max_allowed INT DEFAULT 3,
  
  -- Current state
  blocked_until TIMESTAMPTZ,
  stop_reason TEXT,
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reorg_track_team ON reorganisation_tracking(team_id);
CREATE INDEX idx_reorg_track_task ON reorganisation_tracking(task_id);

-- ============================================================================
-- 18. DEDUPLICATION REGISTRIES
-- ============================================================================

CREATE TABLE organisational_dedup_registry (
  dedup_id UUID PRIMARY KEY,
  
  dedup_type TEXT NOT NULL,  -- proposal, team, decision
  source_hash TEXT NOT NULL UNIQUE,  -- SHA256 of canonical content
  canonical_entity_id UUID NOT NULL,
  duplicate_count INT DEFAULT 1,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_dedup_type CHECK (dedup_type IN ('proposal', 'team', 'decision'))
);

CREATE INDEX idx_dedup_hash ON organisational_dedup_registry(source_hash);

-- ============================================================================
-- 19. CAPABILITY REQUIREMENTS REGISTRY
-- ============================================================================

CREATE TABLE capability_requirements (
  requirement_id UUID PRIMARY KEY,
  
  structure_id UUID NOT NULL REFERENCES organisational_structures(structure_id),
  role_id UUID NOT NULL REFERENCES organisational_roles(role_id),
  
  required_capability TEXT NOT NULL,
  required_level TEXT DEFAULT 'basic',  -- basic, intermediate, advanced
  
  from_node_definition_id UUID REFERENCES node_definitions(definition_id),  -- Where we know who can do this
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cap_req_structure ON capability_requirements(structure_id);
CREATE INDEX idx_cap_req_role ON capability_requirements(role_id);

-- ============================================================================
-- 20. TEMPORARY TEAM DISSOLUTION RECORDS
-- ============================================================================

CREATE TABLE temporary_team_dissolutions (
  dissolution_id UUID PRIMARY KEY,
  
  team_id UUID NOT NULL REFERENCES team_instantiations(team_id),
  
  -- Why it dissolved
  dissolution_reason TEXT,  -- task_complete, task_failed, time_limit, member_unavailable, reorganisation, other
  
  -- Evidence preservation (before cleanup)
  preserved_execution_records JSONB,  -- Summary of executions
  preserved_outcomes JSONB,  -- Task results
  preserved_handoffs JSONB,  -- Handoff history
  
  dissolved_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_dissolutions_team ON temporary_team_dissolutions(team_id);

-- ============================================================================
-- Apply all constraints
-- ============================================================================

ALTER TABLE organisational_structures ADD CONSTRAINT fk_fallback CHECK (fallback_structure_id IS NULL OR fallback_structure_id <> structure_id);

COMMIT;
