from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Profile Manager
--------------------------------------------
"""


from profiles.profile import Profile


class ProfileManager:

    def __init__(self):

        self.profiles = {}

        self.active = None

    ##################################################

    def create(

        self,

        username,

    ):

        profile = Profile(

            username,

        )

        self.profiles[username] = profile

        return profile

    ##################################################

    def remove(

        self,

        username,

    ):

        self.profiles.pop(

            username,

            None,

        )

    ##################################################

    def load(

        self,

        username,

    ):

        self.active = self.profiles.get(

            username,

        )

        return self.active

    ##################################################

    def current(self):

        return self.active

    ##################################################

    def list_profiles(self):

        return list(

            self.profiles.keys()

        )

    ##################################################

    def clear(self):

        self.profiles.clear()

        self.active = None