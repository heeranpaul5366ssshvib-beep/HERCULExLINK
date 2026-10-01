from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Terminal Ability
Author: Heeran Paul
License: MIT
--------------------------------------------

Safe, restricted terminal execution: allowlisted read-only commands,
no shell, timeout enforced, destructive patterns blocked. High-risk:
callers must pass approval_required=True and approved=True (enforced
by AbilityManager). This never permits unrestricted system execution.
"""


import re as _re
import shlex
import subprocess

from abilities.base_ability import BaseAbility


_ALLOWED = {
    "echo": {"echo"},
    "info": {"hostname", "whoami", "python", "pip", "ls", "dir", "cat", "type"},
}

_FLAT_ALLOWED = {"echo", "hostname", "whoami", "python", "pip", "ls", "dir", "cat", "type"}

_BLOCKED = ("&", "|", ";", ">", "<", "`", "$", "rm ", "del ", "format", "shutdown",
            "reboot", "mkfs", "curl", "wget", "ssh", "chmod", "chown", "sudo", "powershell -c")

# Commands that take filesystem operands must stay inside the workspace
# sandbox (absolute paths or parent escapes would allow reads outside it).
_PATH_OPERAND_COMMANDS = {"ls", "dir", "cat", "type"}


def _workspace_safe(operand: str) -> bool:
    from pathlib import Path
    cleaned = (operand or "").strip().strip('"').strip("'")
    if not cleaned or cleaned.startswith("-"):
        return True  # flags carry no path
    candidate = Path(cleaned)
    if candidate.is_absolute():
        return False
    if ".." in candidate.parts:
        return False
    return True


class TerminalAbility(BaseAbility):

    def __init__(self):

        super().__init__(

            "terminal",

            "Execute allowlisted read-only terminal commands",

            capability="TERMINAL_EXECUTE",
            inputs={"command": "allowlisted command string"},
            outputs={"stdout": "command output"},
            permissions=["TERMINAL_EXECUTE"],
            environments={"default"},
            verification="exit status 0, relevant outputs captured",
            timeout_s=10,
            risk="HIGH",

        )

    ##################################################

    def validate_input(self, task, **kwargs):
        command = str(task if isinstance(task, str) else kwargs.get("command", "") or "")
        if not command.strip():
            return "empty command"
        lowered = command.lower()
        if any(pattern in lowered for pattern in _BLOCKED):
            return f"blocked pattern in command: {command[:80]}"
        try:
            parts = shlex.split(command, posix=True)
        except Exception:
            return "unparseable command"
        if not parts or parts[0].lower() not in _FLAT_ALLOWED:
            return f"command not allowlisted: {parts[0] if parts else ''}"
        if parts[0].lower() in _PATH_OPERAND_COMMANDS:
            # Check the RAW text: posix shlex strips backslashes, which
            # would hide Windows absolute paths (C:\...) from inspection.
            if _re.search(r"[a-zA-Z]:[\\/]", command) or "\\\\" in command:
                return ("path escapes workspace sandbox "
                        "(absolute paths are not allowed; use workspace-relative paths)")
            for operand in parts[1:]:
                if not _workspace_safe(operand):
                    return (f"path escapes workspace sandbox: {operand[:80]} "
                            f"(use workspace-relative paths)")
        return ""

    def execute(

        self,

        command: str = "",

        task=None,

        **kwargs,

    ):
        raw = str(command or task or kwargs.get("command", "") or "")
        problem = self.validate_input(raw)
        if problem:
            return {"status": "failed", "command": raw, "error": problem}

        parts = shlex.split(raw, posix=True)
        # Restrict subcommands: python --version, pip list, ls/dir listings.
        head = parts[0].lower()
        if head == "python" and parts[1:] not in ([], ["--version"]):
            return {"status": "failed", "command": raw,
                    "error": "only 'python --version' is allowlisted"}
        if head == "pip" and parts[1:] != ["list"]:
            return {"status": "failed", "command": raw,
                    "error": "only 'pip list' is allowlisted"}

        try:
            result = subprocess.run(
                parts,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "command": raw, "error": "command timed out"}
        except Exception as error:
            return {"status": "failed", "command": raw, "error": str(error)}

        if result.returncode != 0:
            return {"status": "failed", "command": raw, "stdout": result.stdout,
                    "stderr": result.stderr, "returncode": result.returncode,
                    "error": f"non-zero exit {result.returncode}"}
        return {

            "status": "success",

            "command": raw,

            "stdout": result.stdout,

            "stderr": result.stderr,

            "returncode": result.returncode,

        }
