"""
Section 14: Strategy Learning Endpoints

REST API for strategy and method learning management.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import os

from .strategy_learning import StrategyLearningService

router = APIRouter(prefix="/api/v1", tags=["strategy-learning"])

DB_URL = os.getenv('DATABASE_URL', 'postgresql://fabric:***@localhost/learning_fabric')
service = StrategyLearningService(DB_URL)

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CreateStrategyRequest(BaseModel):
    strategy_name: str
    description: str = ''
    domain_applicability: Optional[str] = None
    method_representation: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None

class CreateVersionRequest(BaseModel):
    method_representation: Dict[str, Any]
    constraints: Optional[Dict[str, Any]] = None
    creation_reason: str = 'initial'
    created_by_node_id: Optional[str] = None
    parent_version_id: Optional[str] = None

class RecordExecutionRequest(BaseModel):
    task_id: str
    node_id: str
    assignment_id: Optional[str] = None
    attempt_id: Optional[str] = None
    version_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    execution_status: str = 'completed'

class AddEvidenceRequest(BaseModel):
    evidence_type: str  # success, failure, neutral, insufficient
    execution_id: Optional[str] = None
    outcome_quality: Optional[float] = None
    verification_result: Optional[str] = None
    repair_required: bool = False
    completion: bool = False
    confidence: float = 1.0
    source_node_id: Optional[str] = None
    version_id: Optional[str] = None
    evidence_data: Optional[Dict[str, Any]] = None

class CalculateEffectivenessRequest(BaseModel):
    version_id: Optional[str] = None
    context_scope: Optional[Dict[str, Any]] = None
    min_evidence: int = 2

class CompareStrategiesRequest(BaseModel):
    strategy_id_2: str
    comparison_scope: Optional[Dict[str, Any]] = None
    min_population: int = 2

class RecordRepairRequest(BaseModel):
    execution_id: str
    failure_reason: str
    repair_action: str
    subsequent_result: str = 'unknown'
    repair_effectiveness: float = 0.5

class CreateVariantRequest(BaseModel):
    variant_name: str
    variant_type: str = 'specialization'
    reason: str = ''

class RecordSelectionRequest(BaseModel):
    task_id: str
    observation_type: str  # considered, selected, rejected, executed, evaluated
    node_id: Optional[str] = None
    assignment_id: Optional[str] = None
    rationale: str = ''
    context: Optional[Dict[str, Any]] = None

# ============================================================================
# STRATEGY ENDPOINTS
# ============================================================================

@router.post("/strategies")
async def create_strategy(req: CreateStrategyRequest):
    """Create persistent strategy identity"""
    try:
        strategy_id = service.create_strategy(
            strategy_name=req.strategy_name,
            description=req.description,
            domain_applicability=req.domain_applicability,
            method_representation=req.method_representation,
            constraints=req.constraints,
            provenance=req.provenance
        )
        return {
            'strategy_id': strategy_id,
            'strategy_name': req.strategy_name,
            'domain': req.domain_applicability,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# VERSION ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/versions")
async def create_version(strategy_id: str, req: CreateVersionRequest):
    """Create strategy version"""
    try:
        version_id = service.create_strategy_version(
            strategy_id=strategy_id,
            method_representation=req.method_representation,
            constraints=req.constraints,
            creation_reason=req.creation_reason,
            created_by_node_id=req.created_by_node_id,
            parent_version_id=req.parent_version_id
        )
        return {
            'version_id': version_id,
            'strategy_id': strategy_id,
            'creation_reason': req.creation_reason,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/strategies/{strategy_id}/versions")
async def get_version_history(strategy_id: str):
    """Get strategy version history"""
    try:
        versions = service.get_strategy_version_history(strategy_id)
        return {
            'strategy_id': strategy_id,
            'versions': versions,
            'version_count': len(versions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EXECUTION ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/executions")
async def record_execution(strategy_id: str, req: RecordExecutionRequest):
    """Record strategy execution"""
    try:
        execution_id = service.record_strategy_execution(
            strategy_id=strategy_id,
            task_id=req.task_id,
            node_id=req.node_id,
            assignment_id=req.assignment_id,
            attempt_id=req.attempt_id,
            version_id=req.version_id,
            context=req.context,
            parameters=req.parameters,
            execution_status=req.execution_status
        )
        return {
            'execution_id': execution_id,
            'strategy_id': strategy_id,
            'task_id': req.task_id,
            'node_id': req.node_id,
            'status': 'recorded'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EVIDENCE ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/evidence")
async def add_evidence(strategy_id: str, req: AddEvidenceRequest):
    """Add evidence to strategy"""
    try:
        evidence_id = service.add_evidence(
            strategy_id=strategy_id,
            evidence_type=req.evidence_type,
            execution_id=req.execution_id,
            outcome_quality=req.outcome_quality,
            verification_result=req.verification_result,
            repair_required=req.repair_required,
            completion=req.completion,
            confidence=req.confidence,
            source_node_id=req.source_node_id,
            version_id=req.version_id,
            evidence_data=req.evidence_data
        )
        return {
            'evidence_id': evidence_id,
            'strategy_id': strategy_id,
            'evidence_type': req.evidence_type,
            'status': 'recorded'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# EFFECTIVENESS ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/effectiveness")
async def calculate_effectiveness(strategy_id: str, req: CalculateEffectivenessRequest):
    """Calculate strategy effectiveness"""
    try:
        result = service.calculate_effectiveness(
            strategy_id=strategy_id,
            version_id=req.version_id,
            context_scope=req.context_scope,
            min_evidence=req.min_evidence
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# COMPARISON ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/compare")
async def compare_strategies(strategy_id: str, req: CompareStrategiesRequest):
    """Compare two strategies"""
    try:
        result = service.compare_strategies(
            strategy_id_1=strategy_id,
            strategy_id_2=req.strategy_id_2,
            comparison_scope=req.comparison_scope,
            min_population=req.min_population
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# REPAIR ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/repairs")
async def record_repair(strategy_id: str, req: RecordRepairRequest):
    """Record repair applied to failure"""
    try:
        repair_id = service.record_repair(
            execution_id=req.execution_id,
            strategy_id=strategy_id,
            failure_reason=req.failure_reason,
            repair_action=req.repair_action,
            subsequent_result=req.subsequent_result,
            repair_effectiveness=req.repair_effectiveness
        )
        return {
            'repair_id': repair_id,
            'strategy_id': strategy_id,
            'status': 'recorded'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# VARIANT ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/variants")
async def create_variant(strategy_id: str, req: CreateVariantRequest):
    """Create strategy variant"""
    try:
        variant_id = service.create_variant(
            parent_strategy_id=strategy_id,
            variant_name=req.variant_name,
            variant_type=req.variant_type,
            reason=req.reason
        )
        return {
            'variant_id': variant_id,
            'parent_strategy_id': strategy_id,
            'variant_name': req.variant_name,
            'status': 'created'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# SELECTION OBSERVATION ENDPOINTS
# ============================================================================

@router.post("/strategies/{strategy_id}/selection-observations")
async def record_selection(strategy_id: str, req: RecordSelectionRequest):
    """Record strategy selection observation"""
    try:
        observation_id = service.record_selection_observation(
            task_id=req.task_id,
            strategy_id=strategy_id,
            observation_type=req.observation_type,
            node_id=req.node_id,
            assignment_id=req.assignment_id,
            rationale=req.rationale,
            context=req.context
        )
        return {
            'observation_id': observation_id,
            'strategy_id': strategy_id,
            'observation_type': req.observation_type,
            'status': 'recorded'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# GUIDANCE ENDPOINTS
# ============================================================================

@router.get("/strategies/guidance/{task_type}")
async def get_guidance(
    task_type: str,
    domain: Optional[str] = Query(None),
    include_history: bool = Query(False)
):
    """Get strategy guidance for task type"""
    try:
        guidance = service.get_strategy_guidance(
            task_type=task_type,
            domain=domain,
            include_history=include_history
        )
        return guidance
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
