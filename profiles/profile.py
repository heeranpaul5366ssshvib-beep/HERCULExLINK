from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Profile
--------------------------------------------
"""



class Profile:

    def __init__(

        self,

        username,

    ):

        self.username = username

        self.preferences = {}

        self.permissions = {}

        self.memory = {}

    ##################################################

    def set_preference(

        self,

        key,

        value,

    ):

        self.preferences[key] = value

    ##################################################

    def get_preference(

        self,

        key,

        default=None,

    ):

        return self.preferences.get(

            key,

            default,

        )

    ##################################################

    def set_permission(

        self,

        name,

        value,

    ):

        self.permissions[name] = value

    ##################################################

    def has_permission(

        self,

        name,

    ):

        return self.permissions.get(

            name,

            False,

        )

    ##################################################

    def remember(

        self,

        key,

        value,

    ):

        self.memory[key] = value

    ##################################################

    def recall(

        self,

        key,

    ):

        return self.memory.get(

            key,

        )