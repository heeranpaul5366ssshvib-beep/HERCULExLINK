"""
HERCULE Smart Repair Engine

Provides safe, compatibility-aware automatic repair
for the HERCULE AI Operating System.

Rules
-----
• Never remove working code
• Always create backups
• Validate every repair
• Roll back on failure
"""

from .repair_config import RepairConfig
from .smart_repair_manager import SmartRepairManager
from .repair_engine import RepairEngine

__all__ = [
    "RepairConfig",
    "SmartRepairManager",
    "RepairEngine",
]