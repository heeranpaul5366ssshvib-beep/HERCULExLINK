from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: WebSocket Server
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class WebSocketServer:

    def __init__(self):

        self.running = False

        self.clients = []

    ##################################################

    def start(self):

        self.running = True

    ##################################################

    def stop(self):

        self.running = False

    ##################################################

    def connect(

        self,

        client,

    ):

        self.clients.append(client)

    ##################################################

    def disconnect(

        self,

        client,

    ):

        if client in self.clients:

            self.clients.remove(client)

    ##################################################

    def broadcast(

        self,

        message,

    ):

        for client in self.clients:

            if hasattr(client, "send"):

                client.send(message)