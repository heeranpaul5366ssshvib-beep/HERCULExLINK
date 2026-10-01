from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Model
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class WorldModel:
    """
    Internal representation of the external world.

    Stores knowledge about:

    • Objects
    • People
    • Places
    • Events
    • Time
    • Goals
    • Relationships
    • Environment
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.objects: Dict[str, Dict[str, Any]] = {}

        self.people: Dict[str, Dict[str, Any]] = {}

        self.places: Dict[str, Dict[str, Any]] = {}

        self.events: Dict[str, Dict[str, Any]] = {}

        self.goals: Dict[str, Dict[str, Any]] = {}

        self.relationships: List[Dict[str, Any]] = []

        self.environment: Dict[str, Any] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing World Model")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping World Model")

        self.objects.clear()

        self.people.clear()

        self.places.clear()

        self.events.clear()

        self.goals.clear()

        self.relationships.clear()

        self.environment.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "objects": len(self.objects),

            "people": len(self.people),

            "places": len(self.places),

            "events": len(self.events),

            "goals": len(self.goals),

            "relationships": len(self.relationships),
        }

    # --------------------------------------------------
    # Objects
    # --------------------------------------------------

    def add_object(
        self,
        object_id: str,
        data: Dict[str, Any],
    ):

        self.objects[object_id] = data

    def get_object(
        self,
        object_id: str,
    ) -> Optional[Dict[str, Any]]:

        return self.objects.get(object_id)

    def remove_object(
        self,
        object_id: str,
    ):

        self.objects.pop(object_id, None)

    # --------------------------------------------------
    # People
    # --------------------------------------------------

    def add_person(
        self,
        person_id: str,
        data: Dict[str, Any],
    ):

        self.people[person_id] = data

    def get_person(
        self,
        person_id: str,
    ) -> Optional[Dict[str, Any]]:

        return self.people.get(person_id)

    # --------------------------------------------------
    # Places
    # --------------------------------------------------

    def add_place(
        self,
        place_id: str,
        data: Dict[str, Any],
    ):

        self.places[place_id] = data

    def get_place(
        self,
        place_id: str,
    ) -> Optional[Dict[str, Any]]:

        return self.places.get(place_id)

    # --------------------------------------------------
    # Events
    # --------------------------------------------------

    def add_event(
        self,
        event_id: str,
        data: Dict[str, Any],
    ):

        self.events[event_id] = data

    def get_event(
        self,
        event_id: str,
    ) -> Optional[Dict[str, Any]]:

        return self.events.get(event_id)

    # --------------------------------------------------
    # Goals
    # --------------------------------------------------

    def add_goal(
        self,
        goal_id: str,
        data: Dict[str, Any],
    ):

        self.goals[goal_id] = data

    def get_goal(
        self,
        goal_id: str,
    ) -> Optional[Dict[str, Any]]:

        return self.goals.get(goal_id)

    # --------------------------------------------------
    # Relationships
    # --------------------------------------------------

    def add_relationship(
        self,
        source: str,
        relation: str,
        target: str,
    ):

        self.relationships.append({

            "source": source,

            "relation": relation,

            "target": target,

            "timestamp": datetime.now(timezone.utc).isoformat()

        })

    def get_relationships(
        self,
        entity: str,
    ) -> List[Dict[str, Any]]:

        return [

            r

            for r in self.relationships

            if r["source"] == entity
            or r["target"] == entity

        ]

    # --------------------------------------------------
    # Environment
    # --------------------------------------------------

    def update_environment(
        self,
        key: str,
        value: Any,
    ):

        self.environment[key] = value

    def environment_state(self):

        return self.environment.copy()

    # --------------------------------------------------

    def statistics(self):

        return {

            "objects": len(self.objects),

            "people": len(self.people),

            "places": len(self.places),

            "events": len(self.events),

            "goals": len(self.goals),

            "relationships": len(self.relationships),

            "environment_variables": len(self.environment),

            "initialized": self.initialized,
        }