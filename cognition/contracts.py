from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContractBase:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=utc_now)
    source: str = "system"
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    execution_id: Optional[str] = None
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Intent(ContractBase):
    text: str = ""
    confidence: float = 0.0


@dataclass
class Context(ContractBase):
    prompt: str = ""
    items: List[Dict[str, Any]] = field(default_factory=list)
    token_budget: int = 0
    token_usage: int = 0


@dataclass
class Goal(ContractBase):
    name: str = ""
    description: str = ""
    priority: int = 5
    deadline: Optional[str] = None
    parent_goal_id: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    completion_criteria: List[str] = field(default_factory=list)
    status: str = "active"


@dataclass
class PlanStep(ContractBase):
    sequence: int = 0
    description: str = ""
    goal: str = ""
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    verification_criteria: List[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class Strategy(ContractBase):
    objective: str = ""
    options: List[str] = field(default_factory=list)
    risk: str = "LOW"
    reversibility: str = "unknown"
    cost: float = 0.0
    confidence: float = 0.0
    recommended_option: Optional[str] = None


@dataclass
class ReasoningResult(ContractBase):
    goal_id: Optional[str] = None
    objective: str = ""
    facts: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""


@dataclass
class Plan(ContractBase):
    goal_id: Optional[str] = None
    steps: List[PlanStep] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    expected_outcomes: List[str] = field(default_factory=list)
    verification_criteria: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    constraints: List[str] = field(default_factory=list)


@dataclass
class Decision(ContractBase):
    options: List[str] = field(default_factory=list)
    selected_option: Optional[str] = None
    rationale: Dict[str, Any] = field(default_factory=dict)
    risk: str = "LOW"
    confidence: float = 0.0


@dataclass
class Task(ContractBase):
    goal_id: Optional[str] = None
    description: str = ""
    parent_task_id: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    status: str = "created"
    timeout_seconds: int = 60
    required_permissions: List[str] = field(default_factory=list)
    expected_result: Any = None


@dataclass
class Action(ContractBase):
    task_id: Optional[str] = None
    tool_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    authorized: bool = False
    status: str = "proposed"


@dataclass
class Observation(ContractBase):
    source: str = "system"
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True


@dataclass
class VerificationResult(ContractBase):
    task_id: Optional[str] = None
    verified: bool = False
    outcome: str = "unknown"
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ReflectionResult(ContractBase):
    goal_id: Optional[str] = None
    execution_summary: str = ""
    observations: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    success: bool = True


@dataclass
class LearningProposal(ContractBase):
    source: str = "reflection"
    proposal_type: str = "workflow"
    description: str = ""
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    accepted: bool = False
