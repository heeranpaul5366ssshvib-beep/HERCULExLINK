from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Authorization Manager
--------------------------------------------
"""



class AuthorizationManager:

    def __init__(self):

        self.permissions = {}

    ##################################################

    def grant(
        self,
        user,
        permission,
    ):

        self.permissions.setdefault(
            user,
            set(),
        ).add(permission)

    ##################################################

    def revoke(
        self,
        user,
        permission,
    ):

        if user in self.permissions:

            self.permissions[user].discard(permission)

    ##################################################

    def has_permission(
        self,
        user,
        permission,
    ):

        return permission in self.permissions.get(
            user,
            set(),
        )