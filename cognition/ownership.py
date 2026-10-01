from __future__ import annotations

from typing import Dict, List


RESPONSIBILITY_MATRIX = [
    {
        "Responsibility": "context construction",
        "Component": "ContextEngine",
        "Inputs": "prompt, memory, knowledge, task state, tools, environment",
        "Outputs": "ranked context payload with correlation IDs",
        "Callers": "Brain, Orchestrator, CognitionManager",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.context.context_engine.ContextEngine",
    },
    {
        "Responsibility": "relevance / prioritization",
        "Component": "AttentionEngine",
        "Inputs": "context items and metadata",
        "Outputs": "ranked, filtered, relevance-scored items",
        "Callers": "ContextEngine",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.attention.attention_engine.AttentionEngine",
    },
    {
        "Responsibility": "goal management",
        "Component": "GoalManager",
        "Inputs": "goal objects and constraints",
        "Outputs": "active/completed goals",
        "Callers": "Brain, CognitionManager",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.goals.goal_manager.GoalManager",
    },
    {
        "Responsibility": "reasoning",
        "Component": "Reasoner",
        "Inputs": "goal, context, memory, knowledge, constraints",
        "Outputs": "ReasoningResult",
        "Callers": "Brain, CognitionManager",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.reasoning.reasoner.Reasoner",
    },
    {
        "Responsibility": "planning",
        "Component": "Planner",
        "Inputs": "goal, constraints, reasoning, capabilities, permissions",
        "Outputs": "Plan",
        "Callers": "Brain, CognitionManager, Orchestrator",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.planner.planner.Planner",
    },
    {
        "Responsibility": "strategy alternatives",
        "Component": "StrategyEngine",
        "Inputs": "objective, options, constraints, risks, reversibility, cost",
        "Outputs": "Strategy",
        "Callers": "DecisionEngine, Brain",
        "Authority": "Authoritative",
        "Status": "conceptual",
        "module": "cognition.strategy.strategy_engine.StrategyEngine",
    },
    {
        "Responsibility": "decision making",
        "Component": "DecisionEngine",
        "Inputs": "options, constraints, risks, confidence, cost",
        "Outputs": "Decision",
        "Callers": "Brain, CognitionManager, Orchestrator",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.decision.decision_engine.DecisionEngine",
    },
    {
        "Responsibility": "high-level coordination",
        "Component": "Brain",
        "Inputs": "intent, goals, context, model/router outputs",
        "Outputs": "reasoning, plans, execution spark, memory updates",
        "Callers": "runtime, orchestrator, agent callers",
        "Authority": "Coordinator",
        "Status": "active",
        "module": "brain.brain.Brain",
    },
    {
        "Responsibility": "execution coordination",
        "Component": "Orchestrator",
        "Inputs": "approved plan, tasks, agent requests, tools",
        "Outputs": "task execution and dependency orchestration",
        "Callers": "Brain, runtime",
        "Authority": "Execution owner",
        "Status": "active",
        "module": "orchestrator.orchestrator.Orchestrator",
    },
    {
        "Responsibility": "durable task lifecycle",
        "Component": "TaskManager",
        "Inputs": "task state, dependencies, permissions, checkpoints",
        "Outputs": "task status transitions and recovery",
        "Callers": "Orchestrator, Brain, agents",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.task_manager.task_manager.TaskManager",
    },
    {
        "Responsibility": "tool execution",
        "Component": "AbilityManager / ToolExecutor",
        "Inputs": "authorized action + policy + tool metadata",
        "Outputs": "tool result and audit record",
        "Callers": "Orchestrator",
        "Authority": "Execution boundary",
        "Status": "active",
        "module": "abilities.ability_manager.AbilityManager",
    },
    {
        "Responsibility": "authorization",
        "Component": "Security / PolicyManager",
        "Inputs": "capability, risk, actor, approval state",
        "Outputs": "allowed/denied policy decision",
        "Callers": "AbilityManager, TaskManager, Orchestrator",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "security.permissions.policy_manager.PolicyManager",
    },
    {
        "Responsibility": "outcome verification",
        "Component": "VerificationEngine",
        "Inputs": "expected outcome and actual observation",
        "Outputs": "VerificationResult",
        "Callers": "Orchestrator, Brain, TaskManager",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "cognition.task_manager.task_manager.TaskManager",
    },
    {
        "Responsibility": "persistent memory access",
        "Component": "MemoryManager",
        "Inputs": "memory queries and write requests",
        "Outputs": "memory retrieval and persistence",
        "Callers": "Reasoner, Planner, Brain, ContextEngine",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "memory.memory_manager.MemoryManager",
    },
    {
        "Responsibility": "model selection",
        "Component": "ModelRouter",
        "Inputs": "task capability and adapter health",
        "Outputs": "selected adapter/model",
        "Callers": "ModelManager, reasoning/planning callers",
        "Authority": "Authoritative",
        "Status": "active",
        "module": "models.router.model_router.ModelRouter",
    },
    {
        "Responsibility": "learning",
        "Component": "LearningEngine",
        "Inputs": "approved outcomes and evaluations",
        "Outputs": "knowledge candidates and recommendations",
        "Callers": "Brain, reflection layer",
        "Authority": "Supportive",
        "Status": "active",
        "module": "cognition.learning.learning_manager.LearningEngine",
    },
    {
        "Responsibility": "reflection",
        "Component": "ReflectionEngine",
        "Inputs": "goal, plan, execution history, observations",
        "Outputs": "success/failure analysis, improvement suggestions",
        "Callers": "Brain",
        "Authority": "Supportive",
        "Status": "active",
        "module": "cognition.reflection.reflection_engine.ReflectionEngine",
    },
]


def responsibility_matrix() -> List[Dict[str, str]]:
    return [
        {
            "Responsibility": row["Responsibility"],
            "Component": row["Component"],
            "Inputs": row["Inputs"],
            "Outputs": row["Outputs"],
            "Callers": row["Callers"],
            "Authority": row["Authority"],
            "Status": row["Status"],
        }
        for row in RESPONSIBILITY_MATRIX
    ]


def get_authoritative_owner(responsibility: str) -> str:
    responsibility_key = str(responsibility).lower().strip()
    aliases = {
        "reasoning": "cognition.reasoning.reasoner.Reasoner",
        "planning": "cognition.planner.planner.Planner",
        "decision": "cognition.decision.decision_engine.DecisionEngine",
        "decision making": "cognition.decision.decision_engine.DecisionEngine",
        "task lifecycle": "cognition.task_manager.task_manager.TaskManager",
        "memory": "memory.memory_manager.MemoryManager",
        "memory persistence": "memory.memory_manager.MemoryManager",
        "model selection": "models.router.model_router.ModelRouter",
        "authorization": "security.permissions.policy_manager.PolicyManager",
        "security": "security.permissions.policy_manager.PolicyManager",
        "tool execution": "abilities.ability_manager.AbilityManager",
        "verification": "cognition.task_manager.task_manager.TaskManager",
        "verification result": "cognition.task_manager.task_manager.TaskManager",
    }
    if responsibility_key in aliases:
        return aliases[responsibility_key]
    for row in RESPONSIBILITY_MATRIX:
        if str(row["Responsibility"]).lower() == responsibility_key:
            return row["module"]
    raise KeyError(f"No authoritative owner registered for '{responsibility}'")
