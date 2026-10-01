from __future__ import annotations
from system.guardian_patch import UniversalFallbackMixin
"""
--------------------------------------------
HERCULE AI Operating System
Module: System Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from system.config.config_manager import ConfigManager
from system.logging.logger import Logger
from system.health.health_monitor import HealthMonitor
from system.diagnostics.diagonistics_manager import DiagnosticsManager
from system.monitoring.monitoring_manager import MonitoringManager
from system.storage.storage_manager import StorageManager
from system.updater.update_manager import UpdateManager


class SystemManager(UniversalFallbackMixin):
    """
    ==========================================
            HERCULE SYSTEM MANAGER
    ==========================================

    Central runtime manager.

    Responsible for

    • Configuration
    • Logging
    • Diagnostics
    • Health Monitoring
    • Storage
    • Updates
    • Runtime Status

    Future

    • Process Manager
    • Resource Manager
    • Scheduler
    • Service Discovery
    • Performance Optimizer
    • Crash Recovery
    • Auto Backup
    • Distributed Runtime
    """

    def __init__(self):

        ##################################################
        # CORE COMPONENTS
        ##################################################

        self.config = ConfigManager()

        self.logger = Logger()

        self.health = HealthMonitor()

        self.diagnostics = DiagnosticsManager()

        self.monitoring = MonitoringManager()

        self.storage = StorageManager()

        self.updater = UpdateManager()

        self.started = False

    ##################################################
    # LIFECYCLE
    ##################################################

    def initialize(self):

        self.config.load()

        self.started = True

        self.logger.info(

            "HERCULE System Initialized"

        )

    ##################################################

    def shutdown(self):

        self.logger.info(

            "HERCULE System Shutdown"

        )

        self.started = False

    ##################################################

    def restart(self):

        self.shutdown()

        self.initialize()

    ##################################################
    # CONFIGURATION
    ##################################################

    def get_config(

        self,

        key,

        default=None,

    ):

        return self.config.get(

            key,

            default,

        )

    ##################################################

    def set_config(

        self,

        key,

        value,

    ):

        self.config.set(

            key,

            value,

        )

        self.config.save()

    ##################################################
    # LOGGING
    ##################################################

    def info(

        self,

        message,

    ):

        self.logger.info(

            message,

        )

    ##################################################

    def warning(

        self,

        message,

    ):

        self.logger.warning(

            message,

        )

    ##################################################

    def error(

        self,

        message,

    ):

        self.logger.error(

            message,

        )

    ##################################################
    # HEALTH
    ##################################################

    def update_health(

        self,

        component,

        status,

    ):

        self.health.update(

            component,

            status,

        )

    ##################################################

    def health_report(self):

        return self.health.report()

    ##################################################
    # DIAGNOSTICS
    ##################################################

    def run_diagnostics(self):

        return self.diagnostics.run()

    ##################################################

    def diagnostics_history(self):

        return self.diagnostics.history()

    ##################################################
    # MONITORING
    ##################################################

    def monitoring_report(self):

        return self.monitoring.snapshot()

    ##################################################

    def uptime(self):

        return self.monitoring.uptime()

    ##################################################
    # STORAGE
    ##################################################

    def create_directory(

        self,

        path,

    ):

        self.storage.create_directory(

            path,

        )

    ##################################################

    def exists(

        self,

        path,

    ):

        return self.storage.exists(

            path,

        )

    ##################################################

    def delete(

        self,

        path,

    ):

        self.storage.delete(

            path,

        )

    ##################################################
    # UPDATES
    ##################################################

    def current_version(self):

        return self.updater.current_version()

    ##################################################

    def check_updates(self):

        return self.updater.check()

    ##################################################

    def install_update(self):

        return self.updater.install()

    ##################################################
    # STATUS
    ##################################################

    def status(self):

        return {

            "started": self.started,

            "healthy": self.health.healthy(),

            "configuration_entries": len(

                self.config.config

            ),

            "version": self.current_version(),

            "uptime": self.uptime(),

        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.shutdown()

        self.initialize()

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def optimize(self):
        """
        Future:
        Runtime optimization.
        """
        pass

    ##################################################

    def cleanup(self):
        """
        Future:
        Clean temporary data.
        """
        pass

    ##################################################

    def backup(self):
        """
        Future:
        Automatic backups.
        """
        pass

    ##################################################

    def restore(self):
        """
        Future:
        Restore from backup.
        """
        pass

    ##################################################

    def performance_report(self):
        """
        Future:
        Performance analytics.
        """
        pass

    ##################################################

    def process_manager(self):
        """
        Future:
        Process management.
        """
        pass

    ##################################################

    def service_manager(self):
        """
        Future:
        Runtime service management.
        """
        pass