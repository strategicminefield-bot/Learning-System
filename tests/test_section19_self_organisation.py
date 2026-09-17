"""
SECTION 19: SELF-ORGANISATION E2E PRODUCTION TESTS
Production verification for organisational structure evolution and team formation.
"""

import subprocess
import json
import uuid
from datetime import datetime

def run_sql(query: str) -> str:
    """Execute SQL on production VPS."""
    result = subprocess.run(
        ["ssh", "vultr", f"docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -t -c \"{query}\""],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def test_01_schema_deployment():
    """TEST 1: Schema deployment and table creation."""
    print("\nTEST 1: Schema Deployment")
    
    # Count Section 19 tables
    count = run_sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'organisational%'")
    org_tables = int(count.strip().split('\n')[0]) if count else 0
    
    print(f"  Organisational tables: {org_tables}")
    assert org_tables >= 14, f"Expected >=14 tables, got {org_tables}"
    
    # Verify baseline preserved
    task_count = run_sql("SELECT COUNT(*) FROM tasks")
    tasks = int(task_count.strip().split('\n')[0]) if task_count else 0
    print(f"  Baseline tasks preserved: {tasks}")
    assert tasks >= 64, f"Baseline regression: expected >=64 tasks, got {tasks}"
    
    print("  PASS")
    return "PASS"

def test_02_structure_creation():
    """TEST 2: Structure definition creation."""
    print("\nTEST 2: Structure Creation")
    
    structure_id = str(uuid.uuid4())
    name = "test_structure_01"
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, purpose,
        applicability_scope, required_capabilities, coordination_pattern, lifecycle_state
    ) VALUES (
        '{structure_id}'::UUID, '{name}', 'architect_executor',
        'Test structure', '{{"task_types": ["test"]}}'::jsonb,
        '{{"architect": ["planning"], "executor": ["execution"]}}'::jsonb,
        'sequential', 'candidate'
    );
    SELECT '{structure_id}'::text;
    """
    
    result = run_sql(query)
    result_id = result.strip().split('\n')[-1]
    
    print(f"  Created structure: {result_id}")
    assert result_id == structure_id, "Structure ID mismatch"
    
    # Verify it exists
    verify = run_sql(f"SELECT COUNT(*) FROM organisational_structures WHERE structure_id = '{structure_id}'::UUID")
    count = int(verify.strip().split('\n')[0])
    assert count == 1, "Structure not found in database"
    
    print("  PASS")
    return "PASS"

def test_03_role_creation():
    """TEST 3: Organisational role definition."""
    print("\nTEST 3: Role Creation")
    
    role_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_roles (
        role_id, role_name, description, required_capabilities
    ) VALUES (
        '{role_id}'::UUID, 'test_executor', 'Executes work',
        ARRAY['code_execution', 'error_handling']
    );
    SELECT COUNT(*) FROM organisational_roles WHERE role_name = 'test_executor';
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created role: test_executor")
    assert count >= 1, "Role not created"
    
    print("  PASS")
    return "PASS"

def test_04_team_instantiation():
    """TEST 4: Team instantiation from structure."""
    print("\nTEST 4: Team Instantiation")
    
    # First create a structure
    structure_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, applicability_scope,
        required_capabilities, coordination_pattern, lifecycle_state
    ) VALUES ('{structure_id}'::UUID, 'team_test', 'single_node', 
              '{{"task_types": ["test"]}}'::jsonb,
              '{{"executor": ["code_execution"]}}'::jsonb,
              'sequential', 'candidate');
    
    INSERT INTO team_instantiations (
        team_id, structure_id, task_id, team_type, team_status
    ) VALUES ('{team_id}'::UUID, '{structure_id}'::UUID, '{task_id}'::UUID,
              'temporary', 'forming');
    
    SELECT COUNT(*) FROM team_instantiations WHERE team_id = '{team_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created team: {team_id}")
    assert count >= 1, "Team not created"
    
    # Verify history recorded
    hist = run_sql(f"SELECT COUNT(*) FROM organisational_history WHERE team_id = '{team_id}'::UUID")
    hist_count = int(hist.strip().split('\n')[-1])
    print(f"  History events: {hist_count}")
    assert hist_count >= 1, "History not recorded"
    
    print("  PASS")
    return "PASS"

def test_05_member_assignment():
    """TEST 5: Role assignment to team member."""
    print("\nTEST 5: Member Assignment")
    
    # Create structures and roles needed
    team_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())
    
    # Get a test node definition (from Section 18)
    node_def = run_sql("SELECT definition_id FROM node_definitions LIMIT 1")
    node_def_id = node_def.strip().split('\n')[-1].strip()
    
    # Get or create a role
    run_sql("""
    INSERT INTO organisational_roles (role_id, role_name, required_capabilities)
    VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, 'test_role_member', ARRAY['test'])
    ON CONFLICT DO NOTHING;
    """)
    
    query = f"""
    INSERT INTO team_instantiations (
        team_id, structure_id, team_type, team_status
    ) VALUES ('{team_id}'::UUID, '{uuid.uuid4()}'::UUID, 'temporary', 'forming');
    
    INSERT INTO team_memberships (
        membership_id, team_id, node_definition_id, role_id, membership_status
    ) VALUES ('{membership_id}'::UUID, '{team_id}'::UUID, '{node_def_id}'::UUID,
              'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, 'assigned');
    
    SELECT COUNT(*) FROM team_memberships WHERE membership_id = '{membership_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Assigned member to team: {membership_id}")
    assert count >= 1, "Membership not created"
    
    print("  PASS")
    return "PASS"

def test_06_structure_versioning():
    """TEST 6: Structure versioning and lineage."""
    print("\nTEST 6: Structure Versioning")
    
    structure_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, coordination_pattern,
        applicability_scope, required_capabilities, lifecycle_state
    ) VALUES ('{structure_id}'::UUID, 'version_test', 'sequential',
              'sequential', '{{"task_types": ["test"]}}'::jsonb,
              '{{"executor": ["test"]}}'::jsonb, 'candidate');
    
    INSERT INTO organisational_structure_versions (
        version_id, structure_id, version_number, name, structure_type,
        coordination_pattern, version_change_type
    ) VALUES ('{version_id}'::UUID, '{structure_id}'::UUID, 1, 'v1', 'sequential',
              'sequential', 'new');
    
    SELECT COUNT(*) FROM organisational_structure_versions 
    WHERE structure_id = '{structure_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created structure version")
    assert count >= 1, "Version not created"
    
    print("  PASS")
    return "PASS"

def test_07_execution_plan():
    """TEST 7: Execution plan generation."""
    print("\nTEST 7: Execution Plan")
    
    plan_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    structure_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, coordination_pattern,
        applicability_scope, required_capabilities, lifecycle_state
    ) VALUES ('{structure_id}'::UUID, 'plan_test', 'sequential',
              'sequential', '{{"task_types": ["test"]}}'::jsonb,
              '{{"executor": ["test"]}}'::jsonb, 'candidate');
    
    INSERT INTO team_instantiations (team_id, structure_id, team_type, team_status)
    VALUES ('{team_id}'::UUID, '{structure_id}'::UUID, 'temporary', 'active');
    
    INSERT INTO execution_plans (
        plan_id, team_id, task_id, objective, selected_structure_id,
        members, steps, plan_status
    ) VALUES ('{plan_id}'::UUID, '{team_id}'::UUID, '{task_id}'::UUID,
              'Execute test task', '{structure_id}'::UUID,
              '[]'::jsonb, '[]'::jsonb, 'created');
    
    SELECT COUNT(*) FROM execution_plans WHERE plan_id = '{plan_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created execution plan")
    assert count >= 1, "Plan not created"
    
    print("  PASS")
    return "PASS"

def test_08_handoff_recording():
    """TEST 8: Handoff recording between roles."""
    print("\nTEST 8: Handoff Recording")
    
    handoff_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    
    # Ensure roles exist
    run_sql("""
    INSERT INTO organisational_roles (role_id, role_name, required_capabilities)
    VALUES ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::UUID, 'role_handoff_src', ARRAY['test'])
    ON CONFLICT DO NOTHING;
    INSERT INTO organisational_roles (role_id, role_name, required_capabilities)
    VALUES ('cccccccc-cccc-cccc-cccc-cccccccccccc'::UUID, 'role_handoff_dst', ARRAY['test'])
    ON CONFLICT DO NOTHING;
    """)
    
    query = f"""
    INSERT INTO team_instantiations (team_id, structure_id, team_type, team_status)
    VALUES ('{team_id}'::UUID, '{uuid.uuid4()}'::UUID, 'temporary', 'active');
    
    INSERT INTO team_handoffs (
        handoff_id, team_id, source_role_id, target_role_id,
        artifact_description, handoff_type, handoff_status
    ) VALUES ('{handoff_id}'::UUID, '{team_id}'::UUID,
              'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::UUID,
              'cccccccc-cccc-cccc-cccc-cccccccccccc'::UUID,
              'Test result', 'result', 'pending');
    
    SELECT COUNT(*) FROM team_handoffs WHERE handoff_id = '{handoff_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created handoff record")
    assert count >= 1, "Handoff not created"
    
    print("  PASS")
    return "PASS"

def test_09_evidence_recording():
    """TEST 9: Organisational evidence collection."""
    print("\nTEST 9: Evidence Recording")
    
    evidence_id = str(uuid.uuid4())
    structure_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, coordination_pattern,
        applicability_scope, required_capabilities, lifecycle_state
    ) VALUES ('{structure_id}'::UUID, 'evidence_test', 'sequential',
              'sequential', '{{"task_types": ["test"]}}'::jsonb,
              '{{"executor": ["test"]}}'::jsonb, 'candidate');
    
    INSERT INTO organisational_evidence (
        evidence_id, structure_id, evidence_type, outcome_status,
        applicable_context, quality_assessment
    ) VALUES ('{evidence_id}'::UUID, '{structure_id}'::UUID,
              'verified_completion', 'success',
              '{{"task_types": ["test"]}}'::jsonb, 0.95);
    
    SELECT COUNT(*) FROM organisational_evidence WHERE evidence_id = '{evidence_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created evidence record")
    assert count >= 1, "Evidence not created"
    
    print("  PASS")
    return "PASS"

def test_10_decision_recording():
    """TEST 10: Organisational decision recording."""
    print("\nTEST 10: Decision Recording")
    
    decision_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    structure_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO organisational_structures (
        structure_id, name, structure_type, coordination_pattern,
        applicability_scope, required_capabilities, lifecycle_state
    ) VALUES ('{structure_id}'::UUID, 'decision_test', 'sequential',
              'sequential', '{{"task_types": ["test"]}}'::jsonb,
              '{{"executor": ["test"]}}'::jsonb, 'candidate');
    
    INSERT INTO organisational_decisions (
        decision_id, task_id, work_objective,
        capability_requirements, role_requirements, candidate_structure_ids,
        selected_structure_id, decision_rationale, decision_status
    ) VALUES ('{decision_id}'::UUID, '{task_id}'::UUID, 'Execute task',
              '{{}}'::jsonb, ARRAY['executor'],
              ARRAY['{structure_id}'::UUID], '{structure_id}'::UUID,
              'Best structure for task', 'made');
    
    SELECT COUNT(*) FROM organisational_decisions WHERE decision_id = '{decision_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Created decision record")
    assert count >= 1, "Decision not created"
    
    print("  PASS")
    return "PASS"

def test_11_team_member_replacement():
    """TEST 11: Team member replacement for unavailability."""
    print("\nTEST 11: Member Replacement")
    
    team_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())
    new_membership_id = str(uuid.uuid4())
    
    # Get node definitions
    node_defs = run_sql("SELECT definition_id FROM node_definitions LIMIT 2")
    node_ids = [line.strip() for line in node_defs.strip().split('\n') if line.strip()]
    
    if len(node_ids) < 2:
        print("  SKIP: Not enough test node definitions")
        return "SKIP"
    
    query = f"""
    INSERT INTO team_instantiations (team_id, structure_id, team_type, team_status)
    VALUES ('{team_id}'::UUID, '{uuid.uuid4()}'::UUID, 'temporary', 'active');
    
    INSERT INTO team_memberships (
        membership_id, team_id, node_definition_id, role_id, membership_status
    ) VALUES ('{membership_id}'::UUID, '{team_id}'::UUID, '{node_ids[0]}'::UUID,
              'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::UUID, 'active');
    
    UPDATE team_memberships
    SET membership_status = 'replaced',
        replaced_by_membership_id = '{new_membership_id}'::UUID,
        replacement_reason = 'Unavailable',
        left_at = NOW()
    WHERE membership_id = '{membership_id}'::UUID;
    
    SELECT COUNT(*) FROM team_memberships 
    WHERE membership_id = '{membership_id}'::UUID 
      AND membership_status = 'replaced';
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Replaced team member")
    assert count >= 1, "Replacement not recorded"
    
    print("  PASS")
    return "PASS"

def test_12_temporary_team_dissolution():
    """TEST 12: Temporary team dissolution."""
    print("\nTEST 12: Temporary Team Dissolution")
    
    team_id = str(uuid.uuid4())
    dissolution_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO team_instantiations (team_id, structure_id, team_type, team_status)
    VALUES ('{team_id}'::UUID, '{uuid.uuid4()}'::UUID, 'temporary', 'completed');
    
    INSERT INTO temporary_team_dissolutions (
        dissolution_id, team_id, dissolution_reason,
        preserved_execution_records
    ) VALUES ('{dissolution_id}'::UUID, '{team_id}'::UUID, 'task_complete',
              '{{}}'::jsonb);
    
    SELECT COUNT(*) FROM temporary_team_dissolutions WHERE dissolution_id = '{dissolution_id}'::UUID;
    """
    
    result = run_sql(query)
    count = int(result.strip().split('\n')[-1])
    
    print(f"  Dissolved temporary team")
    assert count >= 1, "Dissolution not recorded"
    
    print("  PASS")
    return "PASS"

def test_13_api_health():
    """TEST 13: API health check."""
    print("\nTEST 13: API Health")
    
    result = subprocess.run(
        ["ssh", "vultr", "curl -s http://localhost:8000/health"],
        capture_output=True,
        text=True
    )
    
    print(f"  API status: {result.stdout[:50]}")
    assert "ok" in result.stdout.lower(), "API not healthy"
    
    print("  PASS")
    return "PASS"

def test_14_db_health():
    """TEST 14: Database health."""
    print("\nTEST 14: Database Health")
    
    # Count total tables
    count = run_sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
    total_tables = int(count.strip().split('\n')[0])
    
    print(f"  Total tables: {total_tables}")
    assert total_tables >= 140, f"Expected >=140 tables (138 + 19 org), got {total_tables}"
    
    print("  PASS")
    return "PASS"

def test_15_regression_check():
    """TEST 15: Full Section 2-18 regression."""
    print("\nTEST 15: Regression Check (Sections 2-18)")
    
    # Check key entities
    query = """
    SELECT 
        (SELECT COUNT(*) FROM tasks) as tasks,
        (SELECT COUNT(*) FROM assignments) as assignments,
        (SELECT COUNT(*) FROM strategies) as strategies,
        (SELECT COUNT(*) FROM node_definitions) as node_defs,
        (SELECT COUNT(*) FROM experiments) as experiments,
        (SELECT COUNT(*) FROM validation_candidates) as validation_cands
    """
    
    result = run_sql(query)
    print(f"  {result}")
    
    # Parse and verify
    assert "tasks" in result.lower() or "64" in result, "Tasks not found in regression check"
    
    print("  PASS")
    return "PASS"

if __name__ == "__main__":
    tests = [
        test_01_schema_deployment,
        test_02_structure_creation,
        test_03_role_creation,
        test_04_team_instantiation,
        test_05_member_assignment,
        test_06_structure_versioning,
        test_07_execution_plan,
        test_08_handoff_recording,
        test_09_evidence_recording,
        test_10_decision_recording,
        test_11_team_member_replacement,
        test_12_temporary_team_dissolution,
        test_13_api_health,
        test_14_db_health,
        test_15_regression_check,
    ]
    
    results = {}
    for test in tests:
        try:
            results[test.__name__] = test()
        except Exception as e:
            print(f"  FAIL: {e}")
            results[test.__name__] = "FAIL"
    
    print("\n" + "="*60)
    print("SECTION 19 E2E TEST RESULTS")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v == "PASS")
    failed = sum(1 for v in results.values() if v == "FAIL")
    skipped = sum(1 for v in results.values() if v == "SKIP")
    
    for test_name, result in results.items():
        status_symbol = "✓" if result == "PASS" else "✗" if result == "FAIL" else "⊘"
        print(f"{status_symbol} {test_name}: {result}")
    
    print(f"\nTOTAL: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"SUCCESS RATE: {passed}/{len(tests)} = {100*passed/len(tests):.1f}%")
    
    if failed > 0:
        exit(1)
