from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Encryption Manager
--------------------------------------------
"""


import hashlib


class EncryptionManager:

    ##################################################

    def hash(

        self,

        text,

    ):

        return hashlib.sha256(

            text.encode()

        ).hexdigest()

    ##################################################

    def verify(

        self,

        text,

        digest,

    ):

        return self.hash(text) == digest