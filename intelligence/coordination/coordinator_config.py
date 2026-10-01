from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Coordinator Configuration
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class CoordinatorConfig:
    """
    Runtime configuration for the
    Intelligence Coordinator.
    """

    #
    # General
    #

    enabled: bool = True

    auto_initialize: bool = True

    debug: bool = False

    log_level: str = "INFO"

    #
    # Execution
    #

    max_concurrent_tasks: int = 8

    task_queue_size: int = 1000

    task_timeout: float = 300.0

    retry_attempts: int = 3

    retry_delay: float = 1.0

    enable_parallel_execution: bool = True

    #
    # Synchronization
    #

    barrier_timeout: float = 60.0

    synchronization_interval: float = 0.05

    #
    # Monitoring
    #

    enable_health_monitor: bool = True

    enable_metrics: bool = True

    health_check_interval: float = 30.0

    metrics_interval: float = 10.0

    statistics_history: int = 1000

    #
    # Events
    #

    publish_events: bool = True

    event_buffer_size: int = 1000

    #
    # Dependency Graph
    #

    validate_dependencies: bool = True

    detect_cycles: bool = True

    #
    # Execution Graph
    #

    optimize_execution_graph: bool = True

    allow_dynamic_graph_updates: bool = True

    #
    # Runtime
    #

    shutdown_timeout: float = 30.0

    startup_timeout: float = 60.0

    graceful_shutdown: bool = True

    #
    # Future Features
    #

    enable_distributed_execution: bool = False

    enable_remote_workers: bool = False

    enable_gpu_scheduling: bool = False

    enable_predictive_scheduling: bool = False

    enable_self_optimization: bool = False

    enable_self_healing: bool = False

    # --------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)

    # --------------------------------------------------

    @classmethod
    def from_dict(

        cls,

        config: Dict[str, Any],

    ) -> "CoordinatorConfig":

        return cls(**config)

    # --------------------------------------------------

    def update(

        self,

        **kwargs,

    ):

        for key, value in kwargs.items():

            if hasattr(self, key):

                setattr(

                    self,

                    key,

                    value,

                )

    # --------------------------------------------------

    def reset(self):

        defaults = CoordinatorConfig()

        self.__dict__.update(

            defaults.__dict__

        )

    # --------------------------------------------------

    def validate(self) -> bool:

        if self.max_concurrent_tasks <= 0:

            return False

        if self.task_timeout <= 0:

            return False

        if self.retry_attempts < 0:

            return False

        if self.barrier_timeout <= 0:

            return False

        if self.health_check_interval <= 0:

            return False

        return True