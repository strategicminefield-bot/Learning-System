"""
Section 13: Knowledge Evolution Endpoints

REST API for knowledge evolution management.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import os

from .knowledge_evolution import KnowledgeEvolutionService

router = APIRouter(prefix="/api/v1", tags=["knowledge-evolution"])

DB_URL = os.getenv('DATABASE_URL', 'postgresql://fabric:fabric@localhost/learning_fabric')
service = KnowledgeEvolutionService(DB_URL)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateEntityRequest(BaseModel):
    entity_type: str
    task_type: str
    original_source_id: Optional[str] = None

class CreateVersionRequest(BaseModel):
    content: Dict[str, Any]
    parent_version_id: Optional[str] = None
    applicability: Optional[Dict[str, Any]] = None
    validation_state: str = 'confirmed'
    confidence: float = 0.8
    creation_reason: str = 'initial'
    created_by_node_id: Optional[str] = None
    created_by_rule: Optional[str] = None

class AddEvidenceRequest(BaseModel):
    evidence_type: str  # supportive, contradictory, neutral
    source_type: str
    source_id: str
    confidence: float
    source_node_id: Optional[str] = None
    evidence_data: Optional[Dict[str, Any]] = None
    version_id: Optional[str] = None

class EvolveKnowledgeRequest(BaseModel):
    evolution_type: str
    rule_id: Optional[str] = None
    reason: str = ''

class CreateLineageRequest(BaseModel):
    target_entity_id: str
    relationship_type: str
    reason: str = ''
    confidence: float = 1.0
    source_version_id: Optional[str] = None
    target_version_id: Optional[str] = None

class MergeKnowledgeRequest(BaseModel):
    entity_id_2: str
    reason: str = ''
    merge_evidence: Optional[Dict[str, Any]] = None

class RestrictScopeRequest(BaseModel):
    restriction_type: str
    scope_criteria: Dict[str, Any]
    reason: str = ''

class RetireKnowledgeRequest(BaseModel):
    reason: str = ''

# ============================================================================
# ENTITY ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities")
async def create_knowledge_entity(req: CreateEntityRequest):
    """Create persistent knowledge entity identity"""
    try:
        entity_id = service.create_knowledge_entity(
            entity_type=req.entity_type,
            task_type=req.task_type,
            original_source_id=req.original_source_id
        )
        return {
            'entity_id': entity_id,
            'entity_type': req.entity_type,
            'task_type': req.task_type,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# VERSION ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/versions")
async def create_version(entity_id: str, req: CreateVersionRequest):
    """Create knowledge version"""
    try:
        version_id = service.create_version(
            entity_id=entity_id,
            content=req.content,
            parent_version_id=req.parent_version_id,
            applicability=req.applicability,
            validation_state=req.validation_state,
            confidence=req.confidence,
            creation_reason=req.creation_reason,
            created_by_node_id=req.created_by_node_id,
            created_by_rule=req.created_by_rule
        )
        return {
            'version_id': version_id,
            'entity_id': entity_id,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/knowledge-evolution/entities/{entity_id}/effective")
async def get_effective_version(
    entity_id: str,
    at_time: Optional[str] = Query(None)
):
    """Get effective knowledge version at specific time"""
    try:
        at_datetime = None
        if at_time:
            at_datetime = datetime.fromisoformat(at_time)
        
        effective = service.get_effective_version(entity_id, at_datetime)
        if not effective:
            raise HTTPException(status_code=404, detail='No effective version found')
        
        return effective
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EVIDENCE ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/evidence")
async def add_evidence(entity_id: str, req: AddEvidenceRequest):
    """Add evidence to knowledge entity"""
    try:
        evidence_id = service.add_evidence(
            entity_id=entity_id,
            evidence_type=req.evidence_type,
            source_type=req.source_type,
            source_id=req.source_id,
            confidence=req.confidence,
            source_node_id=req.source_node_id,
            evidence_data=req.evidence_data,
            version_id=req.version_id
        )
        return {
            'evidence_id': evidence_id,
            'entity_id': entity_id,
            'evidence_type': req.evidence_type,
            'status': 'recorded'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EVOLUTION ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/evaluate")
async def evaluate_evolution(entity_id: str):
    """Evaluate if knowledge should evolve"""
    try:
        should_evolve, decision, resulting_version = service.evaluate_evolution(entity_id)
        return {
            'entity_id': entity_id,
            'should_evolve': should_evolve,
            'decision': decision,
            'resulting_version_id': resulting_version,
            'status': 'evaluated'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/knowledge-evolution/entities/{entity_id}/evolve")
async def evolve_knowledge(entity_id: str, req: EvolveKnowledgeRequest):
    """Apply knowledge evolution"""
    try:
        decision_id = service.evolve_knowledge(
            entity_id=entity_id,
            evolution_type=req.evolution_type,
            rule_id=req.rule_id,
            reason=req.reason
        )
        return {
            'decision_id': decision_id,
            'entity_id': entity_id,
            'evolution_type': req.evolution_type,
            'status': 'evolved'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# LINEAGE ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/lineage")
async def create_lineage(entity_id: str, req: CreateLineageRequest):
    """Create lineage relationship"""
    try:
        lineage_id = service.create_lineage_relationship(
            source_entity_id=entity_id,
            target_entity_id=req.target_entity_id,
            relationship_type=req.relationship_type,
            reason=req.reason,
            confidence=req.confidence,
            source_version_id=req.source_version_id,
            target_version_id=req.target_version_id
        )
        return {
            'lineage_id': lineage_id,
            'source_entity_id': entity_id,
            'target_entity_id': req.target_entity_id,
            'relationship_type': req.relationship_type,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/knowledge-evolution/entities/{entity_id}/lineage")
async def get_lineage(entity_id: str):
    """Get entity lineage tree"""
    try:
        lineage = service.get_entity_lineage(entity_id)
        return lineage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MERGE ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/merge")
async def merge_knowledge(entity_id: str, req: MergeKnowledgeRequest):
    """Merge two knowledge entities"""
    try:
        merged_id = service.merge_knowledge_entities(
            entity_id_1=entity_id,
            entity_id_2=req.entity_id_2,
            reason=req.reason,
            merge_evidence=req.merge_evidence
        )
        return {
            'merged_entity_id': merged_id,
            'source_entity_1': entity_id,
            'source_entity_2': req.entity_id_2,
            'status': 'merged'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# SCOPE RESTRICTION ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/restrict")
async def restrict_scope(entity_id: str, req: RestrictScopeRequest):
    """Create scope restriction"""
    try:
        restriction_id = service.restrict_knowledge_scope(
            entity_id=entity_id,
            restriction_type=req.restriction_type,
            scope_criteria=req.scope_criteria,
            reason=req.reason
        )
        return {
            'restriction_id': restriction_id,
            'entity_id': entity_id,
            'restriction_type': req.restriction_type,
            'status': 'restricted'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# RETIREMENT ENDPOINTS
# ============================================================================

@router.post("/knowledge-evolution/entities/{entity_id}/retire")
async def retire_knowledge(entity_id: str, req: RetireKnowledgeRequest):
    """Retire knowledge"""
    try:
        state_id = service.retire_knowledge(
            entity_id=entity_id,
            reason=req.reason
        )
        return {
            'state_id': state_id,
            'entity_id': entity_id,
            'status': 'retired'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
