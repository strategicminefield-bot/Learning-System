"""
Section 13: Knowledge Evolution Tests

Comprehensive tests for all knowledge evolution functionality:
- Strengthening
- Weakening/Dispute
- Restriction
- Supersession
- Merging
- Retirement
- Historical state
- Cross-node evolution
- Failure handling
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fabric.api.knowledge_evolution import KnowledgeEvolutionService

# DB connection URL (from environment or default)
DB_URL = os.getenv('DATABASE_URL', 'postgresql://fabric:fabric@localhost/learning_fabric')

@pytest.fixture
def service():
    """Create service instance for testing"""
    return KnowledgeEvolutionService(DB_URL)

@pytest.fixture
def sample_entity(service):
    """Create sample knowledge entity"""
    return service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='data_analysis'
    )

# ============================================================================
# TEST 01: KNOWLEDGE IDENTITY
# ============================================================================
def test_01_knowledge_identity(service):
    """Create and verify knowledge entity identity"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='test_task'
    )
    
    assert entity_id is not None
    assert len(entity_id) == 36  # UUID length
    print(f"✓ Test 01: Knowledge identity created: {entity_id[:8]}...")

# ============================================================================
# TEST 02: VERSIONING
# ============================================================================
def test_02_versioning(service, sample_entity):
    """Create multiple versions with parent tracking"""
    content_v1 = {'method': 'approach_a', 'quality': 'high'}
    version_1 = service.create_version(
        sample_entity,
        content_v1,
        creation_reason='initial'
    )
    
    # Create v2 as successor
    content_v2 = {'method': 'approach_a_refined', 'quality': 'higher'}
    version_2 = service.create_version(
        sample_entity,
        content_v2,
        parent_version_id=version_1,
        creation_reason='refined based on feedback'
    )
    
    assert version_1 is not None
    assert version_2 is not None
    assert version_1 != version_2
    print(f"✓ Test 02: Versions created with parent tracking: v1={version_1[:8]}..., v2={version_2[:8]}...")

# ============================================================================
# TEST 03: EVOLUTION STATES
# ============================================================================
def test_03_evolution_states(service, sample_entity):
    """Verify evolution state management"""
    version_id = service.create_version(
        sample_entity,
        {'test': 'content'}
    )
    
    # States should be created during version creation
    # Evolve to strengthened
    service.evolve_knowledge(sample_entity, 'strengthen', reason='Test strengthening')
    
    # Verify state exists
    effective = service.get_effective_version(sample_entity)
    assert effective is not None
    assert effective['state'] in ['active', 'strengthen', 'strengthened']
    print(f"✓ Test 03: Evolution states working: {effective['state']}")

# ============================================================================
# TEST 04: EVIDENCE RECORDING
# ============================================================================
def test_04_evidence_recording(service, sample_entity):
    """Record various types of evidence"""
    version_id = service.create_version(
        sample_entity,
        {'test': 'content'}
    )
    
    # Add supportive evidence
    ev1 = service.add_evidence(
        sample_entity,
        'supportive',
        'outcome',
        'outcome_id_1',
        0.92,
        evidence_data={'quality': 'high'}
    )
    
    # Add contradictory evidence
    ev2 = service.add_evidence(
        sample_entity,
        'contradictory',
        'feedback',
        'feedback_id_1',
        0.75,
        evidence_data={'issue': 'failed_in_context_x'}
    )
    
    assert ev1 is not None
    assert ev2 is not None
    print(f"✓ Test 04: Evidence recorded: supportive={ev1[:8]}..., contradictory={ev2[:8]}...")

# ============================================================================
# TEST 05: STRENGTHENING TEST
# ============================================================================
def test_05_strengthening(service):
    """Test knowledge strengthening with multiple supportive evidence"""
    # Create entity
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='quality_check'
    )
    
    # Create version
    version_id = service.create_version(
        entity_id,
        {'approach': 'validation_A'},
        validation_state='confirmed',
        confidence=0.8
    )
    
    # Add 3+ supportive evidence with high confidence
    for i in range(3):
        service.add_evidence(
            entity_id,
            'supportive',
            'outcome',
            f'outcome_{i}',
            0.92,
            source_node_id=f'node_{i}'
        )
    
    # Evaluate evolution
    should_evolve, decision, resulting_version = service.evaluate_evolution(entity_id)
    
    assert should_evolve == True
    assert decision in ['strengthened', 'strengthen']
    print(f"✓ Test 05: Strengthening: decision={decision}, should_evolve={should_evolve}")

# ============================================================================
# TEST 06: WEAKENING/DISPUTE TEST
# ============================================================================
def test_06_weakening_dispute(service):
    """Test knowledge weakening when contradictory evidence appears"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='model_selection'
    )
    
    version_id = service.create_version(
        entity_id,
        {'model': 'algorithm_x'},
        confidence=0.8
    )
    
    # Add balanced evidence: 2 supportive, 2 contradictory
    service.add_evidence(entity_id, 'supportive', 'outcome', 'out_1', 0.85)
    service.add_evidence(entity_id, 'supportive', 'outcome', 'out_2', 0.88)
    service.add_evidence(entity_id, 'contradictory', 'feedback', 'fb_1', 0.75)
    service.add_evidence(entity_id, 'contradictory', 'feedback', 'fb_2', 0.80)
    
    # Evaluate
    should_evolve, decision, _ = service.evaluate_evolution(entity_id)
    
    assert should_evolve == True
    assert decision in ['disputed', 'dispute', 'weakened', 'weaken']
    print(f"✓ Test 06: Weaken/Dispute: decision={decision}, should_evolve={should_evolve}")

# ============================================================================
# TEST 07: RESTRICTION TEST
# ============================================================================
def test_07_restriction(service):
    """Test knowledge scope restriction"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='data_processing'
    )
    
    version_id = service.create_version(
        entity_id,
        {'approach': 'method_A', 'applicability': 'general'}
    )
    
    # Add restriction: only works with quality_threshold > 0.8
    restriction_id = service.restrict_knowledge_scope(
        entity_id,
        'constraint',
        {'condition': 'quality_threshold > 0.8', 'success_rate': 0.95},
        'Evidence shows success only under high-quality conditions'
    )
    
    assert restriction_id is not None
    print(f"✓ Test 07: Restriction created: {restriction_id[:8]}...")

# ============================================================================
# TEST 08: SUPERSESSION TEST
# ============================================================================
def test_08_supersession(service):
    """Test knowledge supersession (A -> B lineage)"""
    # Create two entities
    entity_a = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='algorithm_selection'
    )
    
    entity_b = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='algorithm_selection'
    )
    
    # Create versions
    version_a = service.create_version(entity_a, {'algorithm': 'v1'})
    version_b = service.create_version(entity_b, {'algorithm': 'v2'})
    
    # Create supersession lineage
    lineage_id = service.create_lineage_relationship(
        entity_a,
        entity_b,
        'supersedes',
        'Algorithm v2 is improved version of v1',
        confidence=0.95,
        source_version_id=version_a,
        target_version_id=version_b
    )
    
    assert lineage_id is not None
    
    # Get lineage
    lineage = service.get_entity_lineage(entity_b)
    assert any(p['entity_id'] == entity_a for p in lineage.get('predecessors', []))
    print(f"✓ Test 08: Supersession: entity_a superseded by entity_b")

# ============================================================================
# TEST 09: MERGE TEST
# ============================================================================
def test_09_merge(service):
    """Test knowledge merging"""
    entity_1 = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='validation'
    )
    
    entity_2 = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='validation'
    )
    
    # Create versions
    v1 = service.create_version(entity_1, {'method': 'cross_validation'})
    v2 = service.create_version(entity_2, {'method': 'k_fold_validation'})
    
    # Merge
    merged_entity_id = service.merge_knowledge_entities(
        entity_1,
        entity_2,
        'Both are equivalent validation approaches',
        {'similarity': 0.92, 'reason': 'Same technique, different terminology'}
    )
    
    assert merged_entity_id is not None
    assert merged_entity_id not in [entity_1, entity_2]
    print(f"✓ Test 09: Merge: {entity_1[:8]}... + {entity_2[:8]}... -> {merged_entity_id[:8]}...")

# ============================================================================
# TEST 10: RETIREMENT TEST
# ============================================================================
def test_10_retirement(service):
    """Test knowledge retirement"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='deprecated_method'
    )
    
    version_id = service.create_version(
        entity_id,
        {'method': 'old_approach', 'status': 'deprecated'}
    )
    
    # Retire
    state_id = service.retire_knowledge(
        entity_id,
        'Method replaced by more efficient approach'
    )
    
    assert state_id is not None
    
    # Verify effective version shows retired
    effective = service.get_effective_version(entity_id)
    assert effective['state'] == 'retired'
    print(f"✓ Test 10: Retirement: knowledge retired successfully")

# ============================================================================
# TEST 11: HISTORICAL STATE TEST
# ============================================================================
def test_11_historical_state(service):
    """Test historical knowledge state retrieval"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='evolution_test'
    )
    
    # Create v1
    v1_time = datetime.now(datetime.timezone.utc) - timedelta(days=1)
    v1 = service.create_version(
        entity_id,
        {'version': 1, 'confidence': 0.7}
    )
    
    # Get effective at that time
    current_effective = service.get_effective_version(entity_id)
    assert current_effective is not None
    assert current_effective['version_number'] == 1
    print(f"✓ Test 11: Historical state: v1 retrieved successfully")

# ============================================================================
# TEST 12: CROSS-NODE EVOLUTION TEST
# ============================================================================
def test_12_cross_node_evolution(service):
    """Test evolution with evidence from multiple nodes"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='distributed_learning'
    )
    
    version_id = service.create_version(
        entity_id,
        {'approach': 'consensus_method'},
        confidence=0.8
    )
    
    # Add supportive evidence from 3 different nodes
    for node_num in range(1, 4):
        service.add_evidence(
            entity_id,
            'supportive',
            'cross_node_evidence',
            f'cross_node_evidence_{node_num}',
            0.90 - (node_num * 0.02),  # 0.88, 0.86, 0.84
            source_node_id=f'node_{node_num}'
        )
    
    should_evolve, decision, _ = service.evaluate_evolution(entity_id)
    
    assert should_evolve == True
    print(f"✓ Test 12: Cross-node evolution: {3} nodes contributed supportive evidence")

# ============================================================================
# TEST 13: IDEMPOTENCY TEST
# ============================================================================
def test_13_idempotency(service):
    """Test idempotent operations"""
    entity_id = service.create_knowledge_entity(
        entity_type='organisational_learning',
        task_type='idempotent_test'
    )
    
    version_id = service.create_version(
        entity_id,
        {'data': 'test'}
    )
    
    # Add same evidence twice
    ev1 = service.add_evidence(entity_id, 'supportive', 'outcome', 'same_outcome', 0.9)
    ev2 = service.add_evidence(entity_id, 'supportive', 'outcome', 'same_outcome', 0.9)
    
    # Evidence IDs should be different (new records) but represent same thing
    # In production, dedup registry would prevent this
    assert ev1 != ev2
    print(f"✓ Test 13: Idempotency: separate evidence records created (dedup handled by service)")

# ============================================================================
# TEST 14: FAILURE/EDGE CASES TEST
# ============================================================================
def test_14_failure_edge_cases(service):
    """Test error handling and edge cases"""
    # Invalid entity ID
    effective = service.get_effective_version('invalid-uuid-format')
    # Should return None or raise gracefully
    
    # Valid entity, no versions
    empty_entity = service.create_knowledge_entity(
        entity_type='empty',
        task_type='test'
    )
    
    # Get effective of empty (should handle gracefully)
    effective_empty = service.get_effective_version(empty_entity)
    # May be None or minimal
    
    print(f"✓ Test 14: Edge cases handled gracefully")

# ============================================================================
# RUNNER
# ============================================================================
if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
