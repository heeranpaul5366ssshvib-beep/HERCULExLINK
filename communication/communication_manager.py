from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Communication Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from communication.console.console_interface import ConsoleInterface
from communication.api.api_server import APIServer
from communication.websocket.websocket_server import WebSocketServer
from communication.desktop.desktop_interface import DesktopInterface
from communication.mobile.mobile_interface import MobileInterface
from communication.web.web_interface import WebInterface


class CommunicationManager:
    """
    ==========================================
        HERCULE COMMUNICATION MANAGER
    ==========================================

    Central communication hub.

    Responsible for:

    • Console
    • API
    • WebSocket
    • Desktop
    • Mobile
    • Web

    Future

    • Voice Interface
    • Email
    • SMS
    • Discord
    • Telegram
    • Slack
    • Remote Control
    • Multi-user Sessions
    """

    def __init__(self):

        ##################################################
        # INTERFACES
        ##################################################

        self.console = ConsoleInterface()

        self.api = APIServer()

        self.websocket = WebSocketServer()

        self.desktop = DesktopInterface()

        self.mobile = MobileInterface()

        self.web = WebInterface()

    ##################################################
    # LIFECYCLE
    ##################################################

    def start(self):

        self.console.start()

        self.api.start()

        self.websocket.start()

        self.desktop.start()

        self.mobile.connect()

        self.web.start()

    ##################################################

    def stop(self):

        self.web.stop()

        self.mobile.disconnect()

        self.desktop.stop()

        self.websocket.stop()

        self.api.stop()

        self.console.stop()

    ##################################################
    # CONSOLE
    ##################################################

    def print(

        self,

        message,

    ):

        self.console.output(

            message,

        )

    ##################################################

    def input(self):

        return self.console.input()

    ##################################################
    # WEBSOCKET
    ##################################################

    def broadcast(

        self,

        message,

    ):

        self.websocket.broadcast(

            message,

        )

    ##################################################
    # DESKTOP
    ##################################################

    def send_desktop(

        self,

        message,

    ):

        return self.desktop.send(

            message,

        )

    ##################################################
    # MOBILE
    ##################################################

    def send_mobile(

        self,

        message,

    ):

        return self.mobile.send(

            message,

        )

    ##################################################
    # WEB
    ##################################################

    def send_web(

        self,

        message,

    ):

        return self.web.send(

            message,

        )

    ##################################################
    # STATUS
    ##################################################

    def health(self):

        return {

            "console": True,

            "api": self.api.status(),

            "websocket": self.websocket.running,

            "desktop": self.desktop.status(),

            "mobile": self.mobile.status(),

            "web": self.web.status(),

            "clients": len(

                self.websocket.clients

            ),

        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.stop()

        self.start()

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def start_voice_interface(self):
        """
        Future:
        Voice conversations.
        """
        pass

    ##################################################

    def stop_voice_interface(self):
        """
        Future:
        Stop voice interface.
        """
        pass

    ##################################################

    def send_email(self):
        """
        Future:
        Email support.
        """
        pass

    ##################################################

    def send_sms(self):
        """
        Future:
        SMS support.
        """
        pass

    ##################################################

    def start_discord_bot(self):
        """
        Future:
        Discord integration.
        """
        pass

    ##################################################

    def start_telegram_bot(self):
        """
        Future:
        Telegram integration.
        """
        pass

    ##################################################

    def start_slack_bot(self):
        """
        Future:
        Slack integration.
        """
        pass

    ##################################################

    def remote_connect(self):
        """
        Future:
        Remote AI access.
        """
        pass

    ##################################################

    def synchronize(self):
        """
        Future:
        Synchronize all
        communication channels.
        """
        pass