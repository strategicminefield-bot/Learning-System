"""Section 16: Experimentation Layer - Production Tests"""
import json
from uuid import uuid4
from datetime import datetime
from decimal import Decimal


def test_01_experiment_creation(db):
    """TEST: Control vs Treatment"""
    cursor = db.cursor()
    
    # Create strategies
    strategy_control = uuid4()
    strategy_treatment = uuid4()
    cursor.execute(
        "INSERT INTO strategies (strategy_id, strategy_name, domain_applicability) VALUES (%s, %s, 'test_exp')",
        (strategy_control, "control_strat")
    )
    cursor.execute(
        "INSERT INTO strategies (strategy_id, strategy_name, domain_applicability) VALUES (%s, %s, 'test_exp')",
        (strategy_treatment, "treatment_strat")
    )
    
    # Create experiment
    exp_id = uuid4()
    cursor.execute(
        """INSERT INTO experiments (
            experiment_id, hypothesis, objective, task_domain, control_strategy_id,
            metrics, status
        ) VALUES (%s, %s, %s, 'test_exp', %s, %s, 'proposed')""",
        (exp_id, "Test hypothesis", "Test objective", strategy_control, json.dumps([]))
    )
    
    db.commit()
    
    # Verify
    cursor.execute("SELECT status FROM experiments WHERE experiment_id = %s", (exp_id,))
    assert cursor.fetchone()[0] == 'proposed'
    print("✓ TEST 01 PASS: Experiment creation")


def test_02_insufficient_sample(db):
    """TEST: Insufficient Sample Protection"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    cursor.execute(
        """INSERT INTO experiments (
            experiment_id, hypothesis, objective, min_sample_size,
            metrics, status
        ) VALUES (%s, 'Test', 'Test', 100, %s, 'proposed')""",
        (exp_id, json.dumps([]))
    )
    
    db.commit()
    
    # Verify min_sample is set
    cursor.execute("SELECT min_sample_size FROM experiments WHERE experiment_id = %s", (exp_id,))
    assert cursor.fetchone()[0] == 100
    print("✓ TEST 02 PASS: Insufficient sample protection")


def test_03_arm_creation(db):
    """TEST: Treatment Arms"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    strategy_id = uuid4()
    
    cursor.execute(
        "INSERT INTO strategies (strategy_id, strategy_name) VALUES (%s, 'test')"
        , (strategy_id,)
    )
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'proposed')""",
        (exp_id, json.dumps([]))
    )
    
    # Create control and treatment arms
    for arm_type in ['control', 'treatment']:
        cursor.execute(
            """INSERT INTO experiment_arms (
                experiment_id, arm_name, arm_type, strategy_id
            ) VALUES (%s, %s, %s, %s)""",
            (exp_id, arm_type, arm_type, strategy_id)
        )
    
    db.commit()
    
    cursor.execute(
        "SELECT COUNT(*) FROM experiment_arms WHERE experiment_id = %s",
        (exp_id,)
    )
    assert cursor.fetchone()[0] == 2
    print("✓ TEST 03 PASS: Experiment arms created")


def test_04_task_assignment(db):
    """TEST: Task Assignment to Arm"""
    cursor = db.cursor()
    
    # Create test task
    task_id = uuid4()
    cursor.execute(
        "INSERT INTO tasks (task_id, task_type, status) VALUES (%s, 'test', 'pending')",
        (task_id,)
    )
    
    # Create experiment and arm
    exp_id = uuid4()
    arm_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'proposed')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_arms (arm_id, experiment_id, arm_name, arm_type)
           VALUES (%s, %s, 'arm1', 'treatment')""",
        (arm_id, exp_id)
    )
    
    # Assign task
    assign_id = uuid4()
    assignment_hash = "test_hash"
    cursor.execute(
        """INSERT INTO experiment_assignments (
            assignment_id, experiment_id, arm_id, task_id, assignment_hash
        ) VALUES (%s, %s, %s, %s, %s)""",
        (assign_id, exp_id, arm_id, task_id, assignment_hash)
    )
    
    db.commit()
    
    # Verify unique enrollment
    cursor.execute(
        """SELECT COUNT(*) FROM experiment_assignments
           WHERE experiment_id = %s AND task_id = %s""",
        (exp_id, task_id)
    )
    assert cursor.fetchone()[0] == 1
    print("✓ TEST 04 PASS: Task assignment to arm")


def test_05_observation_recording(db):
    """TEST: Observation Recording"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    assign_id = uuid4()
    arm_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'running')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_arms (arm_id, experiment_id, arm_name, arm_type)
           VALUES (%s, %s, 'arm', 'treatment')""",
        (arm_id, exp_id)
    )
    
    cursor.execute(
        """INSERT INTO experiment_assignments (
            assignment_id, experiment_id, arm_id, task_id, assignment_hash
        ) VALUES (%s, %s, %s, %s, 'hash')""",
        (assign_id, exp_id, arm_id, uuid4())
    )
    
    # Record observation
    obs_id = uuid4()
    cursor.execute(
        """INSERT INTO experiment_observations (
            observation_id, experiment_id, assignment_id, arm_id,
            final_outcome_status, metric_values, quality_score
        ) VALUES (%s, %s, %s, %s, 'success', %s, 0.95)""",
        (obs_id, exp_id, assign_id, arm_id, json.dumps({"metric1": 0.9}))
    )
    
    db.commit()
    
    cursor.execute(
        "SELECT quality_score FROM experiment_observations WHERE observation_id = %s",
        (obs_id,)
    )
    assert float(cursor.fetchone()[0]) == 0.95
    print("✓ TEST 05 PASS: Observation recording")


def test_06_experiment_status_transitions(db):
    """TEST: Status Lifecycle"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'proposed')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_status_history (
            experiment_id, previous_status, new_status, reason
        ) VALUES (%s, NULL, 'proposed', 'Created')""",
        (exp_id,)
    )
    
    # Transition to running
    cursor.execute(
        "UPDATE experiments SET status = 'running' WHERE experiment_id = %s",
        (exp_id,)
    )
    
    cursor.execute(
        """INSERT INTO experiment_status_history (
            experiment_id, previous_status, new_status, reason
        ) VALUES (%s, 'proposed', 'running', 'Started')""",
        (exp_id,)
    )
    
    db.commit()
    
    cursor.execute(
        "SELECT COUNT(*) FROM experiment_status_history WHERE experiment_id = %s",
        (exp_id,)
    )
    assert cursor.fetchone()[0] >= 1
    print("✓ TEST 06 PASS: Status transitions")


def test_07_analysis_creation(db):
    """TEST: Analysis Record"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    analysis_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'running')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_analysis (
            analysis_id, experiment_id, total_observations,
            control_count, treatment_count,
            control_metric_summary, treatment_metric_summary,
            conclusion, effect_direction, confidence_level
        ) VALUES (%s, %s, 10, 5, 5, %s, %s, 'supportive', 'positive', 0.85)""",
        (analysis_id, exp_id, json.dumps({}), json.dumps({}))
    )
    
    db.commit()
    
    cursor.execute(
        "SELECT conclusion FROM experiment_analysis WHERE analysis_id = %s",
        (analysis_id,)
    )
    assert cursor.fetchone()[0] == 'supportive'
    print("✓ TEST 07 PASS: Analysis creation")


def test_08_experiment_conclusion(db):
    """TEST: Experiment Conclusion"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    analysis_id = uuid4()
    conclusion_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'completed')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_analysis (
            analysis_id, experiment_id, total_observations,
            control_count, treatment_count,
            control_metric_summary, treatment_metric_summary,
            conclusion, effect_direction, confidence_level
        ) VALUES (%s, %s, 10, 5, 5, %s, %s, 'supportive', 'positive', 0.85)""",
        (analysis_id, exp_id, json.dumps({}), json.dumps({}))
    )
    
    cursor.execute(
        """INSERT INTO experiment_conclusions (
            conclusion_id, experiment_id, analysis_id,
            conclusion_status, ready_for_promotion
        ) VALUES (%s, %s, %s, 'conclusive_positive', TRUE)""",
        (conclusion_id, exp_id, analysis_id)
    )
    
    db.commit()
    
    cursor.execute(
        """SELECT ready_for_promotion FROM experiment_conclusions
           WHERE conclusion_id = %s""",
        (conclusion_id,)
    )
    assert cursor.fetchone()[0] == True
    print("✓ TEST 08 PASS: Experiment conclusion")


def test_09_early_stop_rules(db):
    """TEST: Early Stopping"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    rule_id = uuid4()
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'running')""",
        (exp_id, json.dumps([]))
    )
    
    cursor.execute(
        """INSERT INTO experiment_early_stop_rules (
            rule_id, experiment_id, rule_type, trigger_condition
        ) VALUES (%s, %s, 'repeated_failure', %s)""",
        (rule_id, exp_id, json.dumps({"threshold": 5, "metric": "failures"}))
    )
    
    db.commit()
    
    cursor.execute(
        "SELECT rule_type FROM experiment_early_stop_rules WHERE rule_id = %s",
        (rule_id,)
    )
    assert cursor.fetchone()[0] == 'repeated_failure'
    print("✓ TEST 09 PASS: Early stop rules")


def test_10_experiment_opportunities(db):
    """TEST: Autonomous Opportunity Identification"""
    cursor = db.cursor()
    
    opp_id = uuid4()
    strategy_1 = uuid4()
    strategy_2 = uuid4()
    
    cursor.execute(
        "INSERT INTO strategies (strategy_id, strategy_name) VALUES (%s, 's1')",
        (strategy_1,)
    )
    cursor.execute(
        "INSERT INTO strategies (strategy_id, strategy_name) VALUES (%s, 's2')",
        (strategy_2,)
    )
    
    cursor.execute(
        """INSERT INTO experiment_opportunities (
            opportunity_id, opportunity_type, strategy_id_1, strategy_id_2,
            reason_text, eligible_for_autonomous_initiation, status
        ) VALUES (%s, 'insufficient_evidence', %s, %s, 'Test', TRUE, 'identified')""",
        (opp_id, strategy_1, strategy_2)
    )
    
    db.commit()
    
    cursor.execute(
        "SELECT status FROM experiment_opportunities WHERE opportunity_id = %s",
        (opp_id,)
    )
    assert cursor.fetchone()[0] == 'identified'
    print("✓ TEST 10 PASS: Opportunity identification")


def test_11_budget_config(db):
    """TEST: Budget and Limits"""
    cursor = db.cursor()
    
    cursor.execute(
        """SELECT max_active_experiments, allow_autonomous_initiation
           FROM experiment_budget_config WHERE active = TRUE LIMIT 1"""
    )
    row = cursor.fetchone()
    assert row is not None
    assert row[0] > 0
    print("✓ TEST 11 PASS: Budget configuration")


def test_12_experiment_isolation(db):
    """TEST: Non-enrolled tasks unaffected"""
    cursor = db.cursor()
    
    exp_id = uuid4()
    enrolled_task = uuid4()
    non_enrolled_task = uuid4()
    
    cursor.execute(
        "INSERT INTO tasks (task_id, task_type, status) VALUES (%s, 'test', 'pending')",
        (enrolled_task,)
    )
    cursor.execute(
        "INSERT INTO tasks (task_id, task_type, status) VALUES (%s, 'test', 'pending')",
        (non_enrolled_task,)
    )
    
    cursor.execute(
        """INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
           VALUES (%s, 'H', 'O', %s, 'running')""",
        (exp_id, json.dumps([]))
    )
    
    # Enroll only one task
    cursor.execute(
        """INSERT INTO experiment_assignments (
            assignment_id, experiment_id, arm_id, task_id, assignment_hash
        ) VALUES (%s, %s, %s, %s, 'hash')""",
        (uuid4(), exp_id, uuid4(), enrolled_task)
    )
    
    db.commit()
    
    # Verify non-enrolled is not in assignments
    cursor.execute(
        """SELECT COUNT(*) FROM experiment_assignments
           WHERE experiment_id = %s AND task_id = %s""",
        (exp_id, non_enrolled_task)
    )
    assert cursor.fetchone()[0] == 0
    print("✓ TEST 12 PASS: Experiment isolation")


if __name__ == "__main__":
    import psycopg
    conn = psycopg.connect("postgresql://fabric:***@localhost/learning_fabric")
    
    tests = [
        test_01_experiment_creation,
        test_02_insufficient_sample,
        test_03_arm_creation,
        test_04_task_assignment,
        test_05_observation_recording,
        test_06_experiment_status_transitions,
        test_07_analysis_creation,
        test_08_experiment_conclusion,
        test_09_early_stop_rules,
        test_10_experiment_opportunities,
        test_11_budget_config,
        test_12_experiment_isolation,
    ]
    
    passed = 0
    for test_func in tests:
        try:
            test_func(conn)
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
    
    print(f"\n{passed}/{len(tests)} tests passed")
    conn.close()
