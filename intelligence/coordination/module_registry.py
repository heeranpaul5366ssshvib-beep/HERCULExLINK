from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Module Registry
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    """
    Metadata describing a registered module.
    """

    name: str

    instance: Any

    version: str = "1.0.0"

    enabled: bool = True

    initialized: bool = False

    created: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


class ModuleRegistry:
    """
    Central registry for Intelligence
    Coordinator modules.
    """

    def __init__(self):

        self._modules: Dict[str, ModuleInfo] = {}

        self.initialized = False

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Module Registry"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Module Registry"
        )

        self._modules.clear()

        self.initialized = False

    # --------------------------------------------------

    def register(

        self,

        name: str,

        module: Any,

        version: str = "1.0.0",

        metadata: Optional[
            Dict[str, Any]
        ] = None,

    ) -> None:

        self._modules[name] = ModuleInfo(

            name=name,

            instance=module,

            version=version,

            metadata=metadata or {},

        )

        logger.info(

            "Registered module: %s",

            name,

        )

    # --------------------------------------------------

    def unregister(

        self,

        name: str,

    ) -> bool:

        if name not in self._modules:

            return False

        del self._modules[name]

        return True

    # --------------------------------------------------

    def get(

        self,

        name: str,

    ) -> Optional[Any]:

        module = self._modules.get(name)

        if module is None:

            return None

        return module.instance

    # --------------------------------------------------

    def info(

        self,

        name: str,

    ) -> Optional[ModuleInfo]:

        return self._modules.get(name)

    # --------------------------------------------------

    def exists(

        self,

        name: str,

    ) -> bool:

        return name in self._modules

    # --------------------------------------------------

    def enable(

        self,

        name: str,

    ) -> bool:

        info = self._modules.get(name)

        if info is None:

            return False

        info.enabled = True

        return True

    # --------------------------------------------------

    def disable(

        self,

        name: str,

    ) -> bool:

        info = self._modules.get(name)

        if info is None:

            return False

        info.enabled = False

        return True

    # --------------------------------------------------

    def set_initialized(

        self,

        name: str,

        value: bool,

    ) -> bool:

        info = self._modules.get(name)

        if info is None:

            return False

        info.initialized = value

        return True

    # --------------------------------------------------

    def modules(self) -> List[str]:

        return list(

            self._modules.keys()

        )

    # --------------------------------------------------

    def enabled_modules(self) -> List[str]:

        return [

            name

            for name, info

            in self._modules.items()

            if info.enabled

        ]

    # --------------------------------------------------

    def statistics(self):

        enabled = sum(

            1

            for info

            in self._modules.values()

            if info.enabled

        )

        initialized = sum(

            1

            for info

            in self._modules.values()

            if info.initialized

        )

        return {

            "initialized":
                self.initialized,

            "registered_modules":
                len(self._modules),

            "enabled_modules":
                enabled,

            "initialized_modules":
                initialized,

        }