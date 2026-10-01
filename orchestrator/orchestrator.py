from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Orchestrator
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from kernel.event_bus import EventBus
from cognition.task_manager.task_manager import TaskManager
from orchestrator.dispatcher import Dispatcher
from orchestrator.executor import Executor
from orchestrator.pipeline import Pipeline
from orchestrator.workflow import Workflow
from orchestrator.agent import Agent


def _default_task_store():
    """Durable task location; None disables persistence.

    Defaults to ``data/tasks.json`` (gitignored runtime state);
    ``HERCULE_TASK_STORE`` overrides, and "disabled"/"none"/":memory:"
    select in-memory-only operation (used by tests).
    """
    from system.config.runtime_config import load_runtime_config
    from system.paths import resolve_data_path
    explicit = load_runtime_config().task_store.strip()
    if explicit.lower() in ("disabled", "none", ":memory:"):
        return None
    if explicit:
        return explicit
    return resolve_data_path("data/tasks.json")


class Orchestrator:
    """
    ==========================================
           HERCULE ORCHESTRATOR
    ==========================================

    Central coordinator of HERCULE AI.

    Connects:

    • Memory
    • Knowledge
    • Models
    • Abilities
    • Perception
    • Communication
    • Security
    • System
    """

    def __init__(

        self,

        memory,

        knowledge,

        models,

        abilities,

        perception,

        communication,

        security,

        system,

    ):

        self.memory = memory

        self.knowledge = knowledge

        self.models = models

        self.abilities = abilities

        self.perception = perception

        self.communication = communication

        self.security = security

        self.system = system

        self.dispatcher = Dispatcher()

        self.event_bus = EventBus()

        self.task_manager = TaskManager(
            event_bus=self.event_bus,
            policy=getattr(self.security, "policy", None) if self.security is not None else None,
            storage_path=_default_task_store(),
        )

        self.executor = Executor()

        self.pipeline = Pipeline()

        self.workflow = Workflow()

        self.agent = Agent(

            memory,

            knowledge,

            models,

            abilities,

        )

    ##################################################

    def execute(

        self,

        route,

        *args,

        **kwargs,

    ):

        task = self.dispatcher.dispatch(

            route,

        )

        return self.executor.execute(

            task,

            *args,

            **kwargs,

        )

    ##################################################

    def register(

        self,

        route,

        handler,

    ):

        self.dispatcher.register(

            route,

            handler,

        )

    ##################################################

    def create_task(self, description, **kwargs):
        return self.task_manager.create_task(description, **kwargs)

    def queue_task(self, task_id, priority=None):
        return self.task_manager.queue_task(task_id, priority=priority)

    def start_task(self, task_id):
        return self.task_manager.start(task_id)

    def pause_task(self, task_id):
        return self.task_manager.pause(task_id)

    def resume_task(self, task_id):
        return self.task_manager.resume(task_id)

    def cancel_task(self, task_id):
        return self.task_manager.cancel(task_id)

    def retry_task(self, task_id, **kwargs):
        return self.task_manager.retry(task_id, **kwargs)

    def complete_task(self, task_id, result=None, **kwargs):
        return self.task_manager.complete(task_id, result=result, **kwargs)

    def task_status(self, task_id):
        return self.task_manager.status(task_id)

    def get_task(self, task_id):
        return self.task_manager.get(task_id)

    ##################################################

    def health(self):

        return {

            "dispatcher": self.dispatcher.health(),

            "executor": self.executor.health(),

            "pipeline": self.pipeline.health(),

            "workflow": self.workflow.health(),

            "system": self.system.status(),

            "security": self.security.health(),

            "memory": self.memory.health(),

            "knowledge": self.knowledge.health(),

            "models": self.models.health(),

            "abilities": self.abilities.health(),

            "perception": self.perception.health(),

            "communication": self.communication.health(),

        }

    ##################################################

    def reset(self):

        self.pipeline.reset()

        self.workflow.clear()

        self.executor.clear()

        self.agent.reset()

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def autonomous_mode(self):
        pass

    ##################################################

    def self_improvement(self):
        pass

    ##################################################

    def multi_agent(self):
        pass

    ##################################################

    def distributed_execution(self):
        pass

    ##################################################

    def reasoning_cycle(self):
        pass

    ##################################################

    def planning_cycle(self):
        pass

    ##################################################

    def learning_cycle(self):
        pass
