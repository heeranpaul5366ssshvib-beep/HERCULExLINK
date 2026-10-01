from __future__ import annotations
"""
HERCULE AI Operating System
Module: Automation Ability
Author: Heeran Paul
License: MIT

Real implementation: Task automation using the automation plans system.
"""

import json
import time
from typing import Any, Dict, List, Optional

from abilities.base_ability import BaseAbility


class AutomationAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "automation",
            "Task automation: create, run, and manage automation plans",
            capability="APPLICATION_CONTROL",
            inputs={
                "operation": "create|run|list|get|approve|reject|cancel|status",
                "name": "plan name",
                "description": "plan description",
                "steps": "list of step dicts with action, target, etc.",
                "plan_id": "existing plan ID for run/get/approve/reject/cancel/status",
                "approval": "approve|reject for approval operations",
            },
            outputs={
                "plan_id": "created plan ID",
                "plan": "plan details",
                "plans": "list of plans",
                "status": "plan execution status",
                "result": "execution result",
            },
            permissions=["APPLICATION_CONTROL", "AUTOMATION"],
            environments={"default"},
            verification="plan created/executed, steps verified",
            timeout_s=300,
            risk="HIGH",
        )
        self._plan_manager = None

    def _ensure_plan_manager(self):
        if self._plan_manager is None:
            try:
                from change_proposal_manager import AutomationPlanManager, ChangeProposalManager
                from security.auditing.audit_manager import AuditManager
                audit = AuditManager()
                proposal_manager = ChangeProposalManager(audit)
                self._plan_manager = AutomationPlanManager(proposal_manager, audit)
            except ImportError:
                return None
        return self._plan_manager

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "")
            if not op:
                return "operation is required"
            if op == "create" and not task.get("name"):
                return "create requires name"
            if op in ("run", "get", "approve", "reject", "cancel", "status") and not task.get("plan_id"):
                return f"{op} requires plan_id"
            if op == "create" and not task.get("steps"):
                return "create requires steps"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty automation request"
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if isinstance(task, dict):
            operation = str(task.get("operation", "")).lower()
        else:
            text = str(task or "").lower()
            if "create" in text and "plan" in text:
                operation = "create"
            elif "run" in text and "plan" in text:
                operation = "run"
            elif "list" in text and "plan" in text:
                operation = "list"
            else:
                operation = "list"

        pm = self._ensure_plan_manager()
        if not pm:
            return {"status": "failed", "error": "AutomationPlanManager not available"}

        try:
            if operation == "create":
                return self._create_plan(task, pm)
            elif operation == "run":
                return self._run_plan(task, pm)
            elif operation == "list":
                return self._list_plans(pm)
            elif operation == "get":
                return self._get_plan(task, pm)
            elif operation == "approve":
                return self._approve_plan(task, pm)
            elif operation == "reject":
                return self._reject_plan(task, pm)
            elif operation == "cancel":
                return self._cancel_plan(task, pm)
            elif operation == "status":
                return self._get_status(task, pm)
            else:
                return {"status": "failed", "error": f"unknown operation: {operation}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _create_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        name = task.get("name", f"plan_{int(time.time())}")
        description = task.get("description", "")
        steps = task.get("steps", [])
        if not steps:
            return {"status": "failed", "error": "steps required for create"}
        plan = pm.create_plan(name=name, description=description, steps=steps)
        return {
            "status": "success",
            "operation": "create",
            "plan_id": plan.plan_id,
            "plan": plan.to_dict(),
        }

    def _run_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for run"}
        result = pm.execute_plan(plan_id)
        return {
            "status": "success" if result.get("status") == "completed" else "failed",
            "operation": "run",
            "plan_id": plan_id,
            "result": result,
        }

    def _list_plans(self, pm) -> Dict[str, Any]:
        plans = pm.get_plans_by_workspace("")
        return {
            "status": "success",
            "operation": "list",
            "plans": [p.to_dict() for p in plans],
        }

    def _get_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for get"}
        plan = pm.get_plan(plan_id)
        if not plan:
            return {"status": "failed", "error": f"plan not found: {plan_id}"}
        return {
            "status": "success",
            "operation": "get",
            "plan_id": plan_id,
            "plan": plan.to_dict(),
        }

    def _approve_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for approve"}
        plan = pm.approve_plan(plan_id)
        return {
            "status": "success",
            "operation": "approve",
            "plan_id": plan_id,
            "plan": plan.to_dict(),
        }

    def _reject_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        reason = task.get("reason", "rejected by user")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for reject"}
        plan = pm.reject_plan(plan_id, reason)
        return {
            "status": "success",
            "operation": "reject",
            "plan_id": plan_id,
            "plan": plan.to_dict(),
        }

    def _cancel_plan(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for cancel"}
        plan = pm.cancel_plan(plan_id)
        return {
            "status": "success",
            "operation": "cancel",
            "plan_id": plan_id,
            "plan": plan.to_dict(),
        }

    def _get_status(self, task: Dict[str, Any], pm) -> Dict[str, Any]:
        plan_id = task.get("plan_id")
        if not plan_id:
            return {"status": "failed", "error": "plan_id required for status"}
        plan = pm.get_plan(plan_id)
        if not plan:
            return {"status": "failed", "error": f"plan not found: {plan_id}"}
        return {
            "status": "success",
            "operation": "status",
            "plan_id": plan_id,
            "status": plan.status,
            "steps": [
                {"step_id": s.step_id, "action": s.action, "status": s.status}
                for s in plan.steps
            ],
        }