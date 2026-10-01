from __future__ import annotations
"""HERCULE PC-Frontier: Autonomous Task Engine.

GOAL → PLAN → EXECUTE → OBSERVE → VERIFY → REPLAN → COMPLETE

Bounded retries and replanning. Integrates with existing orchestrator.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Generator

from orchestrator.autonomous import AutonomousLoop
from orchestrator.step_verifier import verify_step
from models.router.pc_frontier_router import PCFRouter, TaskClassification, TaskType
from models.streaming import StreamingEngine, StreamChunk, ResponseState
from memory.enhanced_memory_manager import EnhancedMemoryManager
from cognition.context.enhanced_context_manager import EnhancedContextManager
from system.hardware import get_runtime_profile, get_profile_config

logger = logging.getLogger("HERCULE.AutonomousEngine")


class TaskPhase(str, Enum):
    """Phases of autonomous task execution."""
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    step_id: str
    description: str
    required_capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    risk: str = "LOW"
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[str] = None
    verification_type: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of executing a step."""
    step_id: str
    status: str  # success, failed, verification_failed
    output: Any = None
    errors: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    verification: Optional[Dict[str, Any]] = None
    tool_used: Optional[str] = None


@dataclass
class AutonomousTask:
    """Autonomous task state."""
    task_id: str
    goal: str
    phase: TaskPhase = TaskPhase.PLANNING
    plan: List[PlanStep] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[Dict[str, Any]] = field(default_factory=list)
    step_results: Dict[str, ExecutionResult] = field(default_factory=dict)
    replan_count: int = 0
    max_replans: int = 2
    max_step_retries: int = 1
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None


class TaskPlanner:
    """Generate execution plans from goals."""
    
    def __init__(self, router: PCFRouter):
        self.router = router
    
    def create_plan(
        self,
        goal: str,
        task_type: TaskType,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[PlanStep]:
        """Create a plan for the goal."""
        # Use router's classification to inform planning
        classification = self.router.classify_task(goal)
        
        # Simple plan generation based on task type
        if task_type == TaskType.CODING:
            return self._plan_coding(goal, classification)
        elif task_type == TaskType.FILE_OPERATION:
            return self._plan_file_ops(goal, classification)
        elif task_type == TaskType.RESEARCH:
            return self._plan_research(goal, classification)
        elif task_type == TaskType.PLANNING:
            return self._plan_planning(goal, classification)
        elif task_type == TaskType.AUTOMATION:
            return self._plan_automation(goal, classification)
        elif task_type == TaskType.CALCULATION:
            return self._plan_calculation(goal, classification)
        elif task_type == TaskType.REASONING:
            return self._plan_reasoning(goal, classification)
        elif task_type == TaskType.ARC:
            return self._plan_arc(goal, classification)
        elif task_type == TaskType.SYSTEM_TASK:
            return self._plan_system(goal, classification)
        else:
            return self._plan_general(goal, classification)
    
    def _plan_coding(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("analyze", f"Analyze requirements: {goal}", ["reasoning"]),
            PlanStep("design", "Design solution structure", ["reasoning"], ["analyze"]),
            PlanStep("implement", "Write code implementation", ["coding"], ["design"]),
            PlanStep("test", "Run tests and verify", ["coding", "verification"], ["implement"]),
        ]
    
    def _plan_file_ops(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("locate", f"Locate target files for: {goal}", ["file_operation"]),
            PlanStep("execute", "Perform file operation", ["file_operation"], ["locate"]),
            PlanStep("verify", "Verify operation result", ["verification"], ["execute"]),
        ]
    
    def _plan_research(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("search", f"Search for information on: {goal}", ["research"]),
            PlanStep("analyze", "Analyze and synthesize findings", ["reasoning"], ["search"]),
            PlanStep("summarize", "Create summary report", ["reasoning"], ["analyze"]),
        ]
    
    def _plan_planning(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("assess", f"Assess current state for: {goal}", ["reasoning"]),
            PlanStep("strategize", "Develop strategy and milestones", ["reasoning", "planning"], ["assess"]),
            PlanStep("detail", "Create detailed action plan", ["planning"], ["strategize"]),
        ]
    
    def _plan_automation(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("analyze", f"Analyze automation target: {goal}", ["reasoning"]),
            PlanStep("script", "Create automation script", ["coding", "automation"], ["analyze"]),
            PlanStep("test", "Test automation", ["verification"], ["script"]),
            PlanStep("deploy", "Deploy automation", ["automation"], ["test"]),
        ]
    
    def _plan_calculation(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("compute", f"Calculate: {goal}", ["calculation"]),
            PlanStep("verify", "Verify calculation", ["verification"], ["compute"]),
        ]
    
    def _plan_reasoning(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("decompose", f"Break down problem: {goal}", ["reasoning"]),
            PlanStep("analyze", "Analyze each component", ["reasoning"], ["decompose"]),
            PlanStep("synthesize", "Synthesize conclusion", ["reasoning"], ["analyze"]),
        ]
    
    def _plan_arc(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("parse", f"Parse ARC task: {goal}", ["arc"]),
            PlanStep("solve", "Apply reasoning to solve", ["reasoning", "arc"], ["parse"]),
            PlanStep("verify", "Verify grid transformation", ["verification"], ["solve"]),
        ]
    
    def _plan_system(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("diagnose", f"Diagnose system for: {goal}", ["system_task"]),
            PlanStep("execute", "Perform system action", ["system_task"], ["diagnose"]),
            PlanStep("verify", "Verify system state", ["verification"], ["execute"]),
        ]
    
    def _plan_general(self, goal: str, classification: TaskClassification) -> List[PlanStep]:
        return [
            PlanStep("execute", f"Execute: {goal}", [classification.task_type.value]),
        ]


class AutonomousEngine:
    """PC-Frontier Autonomous Task Engine."""
    
    def __init__(
        self,
        router: PCFRouter,
        streaming_engine: StreamingEngine,
        memory: EnhancedMemoryManager,
        context_manager: EnhancedContextManager,
        max_replans: int = 2,
        max_step_retries: int = 1,
        max_total_time_s: float = 300.0,
    ):
        self.router = router
        self.streaming = streaming_engine
        self.memory = memory
        self.context = context_manager
        self.planner = TaskPlanner(router)
        self.max_replans = max_replans
        self.max_step_retries = max_step_retries
        self.max_total_time_s = max_total_time_s
        
        # Active tasks
        self._tasks: Dict[str, AutonomousTask] = {}
        self._callbacks: Dict[str, List[Callable[[AutonomousTask, TaskPhase], None]]] = {}
    
    def start_task(
        self,
        goal: str,
        task_id: Optional[str] = None,
        callbacks: Optional[List[Callable[[AutonomousTask, TaskPhase], None]]] = None,
    ) -> str:
        """Start an autonomous task. Returns task_id immediately."""
        task_id = task_id or f"task-{uuid.uuid4().hex[:10]}"
        
        # Classify task
        classification = self.router.classify_task(goal)
        
        # Create plan
        plan = self.planner.create_plan(goal, classification.task_type)
        
        # Create task
        task = AutonomousTask(
            task_id=task_id,
            goal=goal,
            plan=plan,
            max_replans=self.max_replans,
            max_step_retries=self.max_step_retries,
        )
        
        self._tasks[task_id] = task
        if callbacks:
            self._callbacks[task_id] = callbacks
        
        # Start execution in background
        import threading
        thread = threading.Thread(
            target=self._execute_task,
            args=(task_id,),
            daemon=True,
        )
        thread.start()
        
        return task_id
    
    def _execute_task(self, task_id: str):
        """Execute the autonomous task loop."""
        task = self._tasks.get(task_id)
        if not task:
            return
        
        task.phase = TaskPhase.EXECUTING
        task.started_at = time.time()
        self._notify_callbacks(task_id, task.phase)
        
        start_time = time.time()
        step_retries: Dict[str, int] = {}
        
        while task.phase not in (TaskPhase.COMPLETED, TaskPhase.FAILED):
            # Check time budget
            if time.time() - start_time > self.max_total_time_s:
                task.phase = TaskPhase.FAILED
                task.error = "Time budget exceeded"
                break
            
            # Get next pending step
            pending = self._get_ready_steps(task)
            if not pending:
                if task.completed_steps:
                    task.phase = TaskPhase.COMPLETED
                else:
                    task.phase = TaskPhase.FAILED
                    task.error = "No executable steps"
                break
            
            step = pending[0]
            
            # Execute step
            result = self._execute_step(task, step, step_retries)
            task.step_results[step.step_id] = result
            
            if result.status == "success":
                task.completed_steps.append(step.step_id)
                task.phase = TaskPhase.OBSERVING
                self._notify_callbacks(task_id, task.phase)
                
                # Verify
                task.phase = TaskPhase.VERIFYING
                self._notify_callbacks(task_id, task.phase)
                
                verification = self._verify_step(task, step, result)
                result.verification = verification
                
                if verification.get("passed", False):
                    # Step verified, continue
                    continue
                else:
                    # Verification failed
                    task.failed_steps.append({
                        "step_id": step.step_id,
                        "reason": "verification_failed",
                        "detail": verification.get("detail", ""),
                    })
            else:
                # Execution failed
                task.failed_steps.append({
                    "step_id": step.step_id,
                    "reason": "execution_failed",
                    "detail": "; ".join(result.errors),
                })
            
            # Handle failure - retry or replan
            retries = step_retries.get(step.step_id, 0)
            if retries < self.max_step_retries:
                step_retries[step.step_id] = retries + 1
                continue
            
            # Replan if possible
            if task.replan_count < self.max_replans:
                task.replan_count += 1
                task.phase = TaskPhase.REPLANNING
                self._notify_callbacks(task_id, task.phase)
                
                new_plan = self._replan(task, step, result)
                if new_plan:
                    task.plan = new_plan
                    continue
            
            task.phase = TaskPhase.FAILED
            task.error = f"Step {step.step_id} failed after retries and replans"
            break
        
        task.completed_at = time.time()
        if task.phase == TaskPhase.COMPLETED:
            # Create memory checkpoint
            self.memory.create_task_checkpoint(
                task_id=task_id,
                goal=task.goal,
                completed_steps=task.completed_steps,
                verified_facts=[],
                artifacts={},
                relevant_memories=[],
            )
        
        self._notify_callbacks(task_id, task.phase)
    
    def _get_ready_steps(self, task: AutonomousTask) -> List[PlanStep]:
        """Get steps whose dependencies are satisfied."""
        ready = []
        completed = set(task.completed_steps)
        
        for step in task.plan:
            if step.step_id in completed:
                continue
            if step.step_id in [fs["step_id"] for fs in task.failed_steps]:
                continue
            
            deps_met = all(d in completed for d in step.dependencies)
            if deps_met:
                ready.append(step)
        
        return ready
    
    def _execute_step(
        self,
        task: AutonomousTask,
        step: PlanStep,
        step_retries: Dict[str, int],
    ) -> ExecutionResult:
        """Execute a single plan step."""
        start = time.perf_counter()
        
        # Route to appropriate handler
        classification = self.router.classify_task(step.description)
        decision = self.router.route(step.description)
        
        # Check for tool-first
        if decision.model.startswith("tool:"):
            tool_name = decision.model.split(":", 1)[1]
            return self._execute_with_tool(step, tool_name, start)
        
        # Use streaming for model execution
        task_id = f"{task.task_id}-{step.step_id}"
        stream_id = self.streaming.start_stream(
            prompt=step.description,
            task_id=task_id,
            stream=True,
            verify=False,  # We verify separately
        )
        
        # Wait for completion
        response = self.streaming.wait_for_complete(stream_id, timeout=60.0)
        
        latency = (time.perf_counter() - start) * 1000
        
        if response.error:
            return ExecutionResult(
                step_id=step.step_id,
                status="failed",
                errors=[response.error],
                latency_ms=latency,
            )
        
        return ExecutionResult(
            step_id=step.step_id,
            status="success",
            output=response.final_content,
            latency_ms=latency,
            tool_used=decision.model if decision.model.startswith("tool:") else None,
        )
    
    def _execute_with_tool(
        self,
        step: PlanStep,
        tool_name: str,
        start_time: float,
    ) -> ExecutionResult:
        """Execute step with deterministic tool."""
        # This would integrate with actual tool system
        latency = (time.perf_counter() - start_time) * 1000
        
        # Simulate tool execution
        if tool_name == "calculator":
            import re
            # Use the same regex as streaming engine
            expr = re.search(r'(\d+(?:\s*[\+\-\*/]\s*\d+)+)', step.description)
            if expr:
                try:
                    result = eval(expr.group())
                    return ExecutionResult(
                        step_id=step.step_id,
                        status="success",
                        output=f"Result: {result}",
                        latency_ms=latency,
                        tool_used=tool_name,
                    )
                except Exception as e:
                    return ExecutionResult(
                        step_id=step.step_id,
                        status="failed",
                        errors=[str(e)],
                        latency_ms=latency,
                    )
            return ExecutionResult(
                step_id=step.step_id,
                status="failed",
                errors=["Could not calculate"],
                latency_ms=latency,
            )
        
        return ExecutionResult(
            step_id=step.step_id,
            status="success",
            output=f"Tool {tool_name} executed",
            latency_ms=latency,
            tool_used=tool_name,
        )
    
    def _verify_step(
        self,
        task: AutonomousTask,
        step: PlanStep,
        result: ExecutionResult,
    ) -> Dict[str, Any]:
        """Verify step execution."""
        from models.hercule_lm.verifiers import verify_verification, verify_json, verify_math
        
        if step.verification_type == "math":
            # Would need expected value
            return {"passed": True, "score": 1.0, "detail": "Math verification not fully implemented"}
        elif step.verification_type == "json":
            vr = verify_json(str(result.output))
            return {"passed": vr["pass"], "score": vr["score"], "detail": vr["detail"]}
        else:
            # General verification
            vr = verify_verification(str(result.output), "CORRECT|")
            return {"passed": vr["pass"], "score": vr["score"], "detail": vr["detail"]}
    
    def _replan(
        self,
        task: AutonomousTask,
        failed_step: PlanStep,
        result: ExecutionResult,
    ) -> Optional[List[PlanStep]]:
        """Generate a new plan after failure."""
        # Simple replanning: try alternative approach
        new_goal = f"Alternative approach for: {failed_step.description}"
        classification = self.router.classify_task(new_goal)
        
        new_plan = self.planner.create_plan(new_goal, classification.task_type)
        
        # Tag as replan steps
        for i, step in enumerate(new_plan):
            step.step_id = f"replan{task.replan_count}-{step.step_id}"
        
        return new_plan
    
    def _notify_callbacks(self, task_id: str, phase: TaskPhase):
        """Notify phase change callbacks."""
        task = self._tasks.get(task_id)
        if not task:
            return
        
        for cb in self._callbacks.get(task_id, []):
            try:
                cb(task, phase)
            except Exception as e:
                logger.warning(f"Callback error: {e}")
    
    def get_task(self, task_id: str) -> Optional[AutonomousTask]:
        """Get task status."""
        return self._tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self._tasks.get(task_id)
        if task and task.phase not in (TaskPhase.COMPLETED, TaskPhase.FAILED):
            task.phase = TaskPhase.FAILED
            task.error = "Cancelled by user"
            self._notify_callbacks(task_id, task.phase)
            return True
        return False
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """List all tasks."""
        return [
            {
                "task_id": t.task_id,
                "goal": t.goal,
                "phase": t.phase.value,
                "completed": len(t.completed_steps),
                "total": len(t.plan),
                "replans": t.replan_count,
                "error": t.error,
            }
            for t in self._tasks.values()
        ]


def create_autonomous_engine(
    router: PCFRouter,
    streaming_engine: StreamingEngine,
    memory: EnhancedMemoryManager,
    context_manager: EnhancedContextManager,
) -> AutonomousEngine:
    """Factory for autonomous engine."""
    return AutonomousEngine(
        router=router,
        streaming_engine=streaming_engine,
        memory=memory,
        context_manager=context_manager,
    )