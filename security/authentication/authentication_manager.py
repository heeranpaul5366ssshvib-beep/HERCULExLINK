from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Authentication Manager
--------------------------------------------
"""



class AuthenticationManager:

    def __init__(self):

        self.users = {}

        self.active_sessions = {}

    ##################################################

    def register(
        self,
        username,
        password,
    ):

        self.users[username] = password

    ##################################################

    def authenticate(
        self,
        username,
        password,
    ):

        return self.users.get(username) == password

    ##################################################

    def create_session(
        self,
        username,
        token,
    ):

        self.active_sessions[token] = username

    ##################################################

    def remove_session(
        self,
        token,
    ):

        self.active_sessions.pop(token, None)