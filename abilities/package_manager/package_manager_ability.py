from __future__ import annotations
"""
HERCULE AI Operating System
Module: Package Manager Ability
Author: Heeran Paul
License: MIT

Real implementation: pip, npm, cargo, go mod package management.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from abilities.base_ability import BaseAbility


class PackageManagerAbility(BaseAbility):

    SUPPORTED_MANAGERS = {
        "pip": {
            "install": ["pip", "install"],
            "uninstall": ["pip", "uninstall", "-y"],
            "list": ["pip", "list", "--format=json"],
            "show": ["pip", "show"],
            "search": ["pip", "search"],
            "check": ["pip", "check"],
        },
        "npm": {
            "install": ["npm", "install"],
            "uninstall": ["npm", "uninstall"],
            "list": ["npm", "list", "--json"],
            "show": ["npm", "view"],
            "search": ["npm", "search"],
            "audit": ["npm", "audit", "--json"],
        },
        "cargo": {
            "install": ["cargo", "install"],
            "uninstall": ["cargo", "uninstall"],
            "list": ["cargo", "install", "--list"],
            "search": ["cargo", "search", "--limit", "10"],
            "update": ["cargo", "update"],
        },
        "go": {
            "install": ["go", "install"],
            "list": ["go", "list", "-m", "all"],
            "get": ["go", "get"],
            "mod": ["go", "mod"],
        },
        "apt": {
            "install": ["apt-get", "install", "-y"],
            "remove": ["apt-get", "remove", "-y"],
            "list": ["dpkg", "-l"],
            "search": ["apt-cache", "search"],
            "update": ["apt-get", "update"],
        },
        "brew": {
            "install": ["brew", "install"],
            "uninstall": ["brew", "uninstall"],
            "list": ["brew", "list", "--json"],
            "search": ["brew", "search"],
            "update": ["brew", "update"],
        },
    }

    def __init__(self):
        super().__init__(
            "package_manager",
            "Package management: install, remove, list, search packages",
            capability="PACKAGE_MANAGE",
            inputs={
                "operation": "install|uninstall|list|show|search|update|audit",
                "manager": "pip|npm|cargo|go|apt|brew (auto-detected)",
                "packages": "package name(s) to install/uninstall",
                "version": "specific version (optional)",
                "flags": "additional flags",
                "cwd": "working directory",
            },
            outputs={
                "installed": "installed packages",
                "removed": "removed packages",
                "packages": "listed packages",
                "info": "package info",
                "stdout": "command output",
                "stderr": "command errors",
            },
            permissions=["PACKAGE_MANAGE", "TERMINAL_EXECUTE"],
            environments={"default"},
            verification="packages installed/removed, list verified",
            timeout_s=120,
            risk="HIGH",
        )

    def _detect_manager(self, cwd: Optional[str] = None) -> str:
        cwd = Path(cwd or ".")
        if (cwd / "package.json").exists() or (cwd / "pnpm-lock.yaml").exists() or (cwd / "yarn.lock").exists():
            return "npm"
        if (cwd / "Cargo.toml").exists():
            return "cargo"
        if (cwd / "go.mod").exists():
            return "go"
        if (cwd / "requirements.txt").exists() or (cwd / "pyproject.toml").exists():
            return "pip"
        if Path("/usr/bin/apt").exists() or Path("/usr/bin/apt-get").exists():
            return "apt"
        if Path("/opt/homebrew/bin/brew").exists() or Path("/usr/local/bin/brew").exists():
            return "brew"
        return "pip"

    def _run(self, cmd: List[str], cwd: Optional[str] = None, timeout: int = 120) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "command timeout", "returncode": -1}
        except FileNotFoundError:
            return {"status": "failed", "error": f"command not found: {cmd[0]}", "returncode": -1}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300], "returncode": -1}

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "")
            if not op:
                return "operation is required"
            if op in ("install", "uninstall") and not task.get("packages"):
                return f"{op} requires packages"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty package manager request"
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if isinstance(task, dict):
            operation = str(task.get("operation", "")).lower()
            manager = task.get("manager") or self._detect_manager(task.get("cwd"))
            packages = task.get("packages", [])
            if isinstance(packages, str):
                packages = [packages]
            version = task.get("version")
            flags = task.get("flags", [])
            cwd = task.get("cwd")
        else:
            text = str(task or "").lower()
            if "install" in text:
                operation = "install"
            elif "remove" in text or "uninstall" in text:
                operation = "uninstall"
            elif "list" in text:
                operation = "list"
            elif "search" in text:
                operation = "search"
            else:
                operation = "list"
            manager = self._detect_manager()
            packages = []
            for word in text.split():
                if word not in ("install", "remove", "uninstall", "list", "search", "package", "packages", "the", "a", "an"):
                    packages.append(word)
            version = None
            flags = []
            cwd = None

        if manager not in self.SUPPORTED_MANAGERS:
            return {"status": "failed", "error": f"unsupported manager: {manager}"}

        mgr_cmds = self.SUPPORTED_MANAGERS[manager]
        if operation not in mgr_cmds:
            return {"status": "failed", "error": f"operation '{operation}' not supported for {manager}"}

        try:
            if operation == "install":
                return self._install(manager, packages, version, flags, cwd, mgr_cmds)
            elif operation == "uninstall":
                return self._uninstall(manager, packages, flags, cwd, mgr_cmds)
            elif operation == "list":
                return self._list(manager, cwd, mgr_cmds)
            elif operation == "show":
                return self._show(manager, packages, cwd, mgr_cmds)
            elif operation == "search":
                return self._search(manager, packages, cwd, mgr_cmds)
            elif operation == "update":
                return self._update(manager, cwd, mgr_cmds)
            elif operation == "audit":
                return self._audit(manager, cwd, mgr_cmds)
            else:
                return {"status": "failed", "error": f"unknown operation: {operation}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _install(self, manager: str, packages: List[str], version: Optional[str], flags: List[str], cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if not packages:
            return {"status": "failed", "error": "packages required for install"}
        installed = []
        for pkg in packages:
            pkg_spec = f"{pkg}=={version}" if version else pkg
            cmd = cmds["install"] + flags + [pkg_spec]
            result = self._run(cmd, cwd)
            if result["status"] == "success":
                installed.append(pkg)
            else:
                return {"status": "failed", "error": result.get("stderr", result.get("error")), "installed": installed}
        return {"status": "success", "operation": "install", "manager": manager, "installed": installed}

    def _uninstall(self, manager: str, packages: List[str], flags: List[str], cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if not packages:
            return {"status": "failed", "error": "packages required for uninstall"}
        removed = []
        for pkg in packages:
            cmd = cmds["uninstall"] + flags + [pkg]
            result = self._run(cmd, cwd)
            if result["status"] == "success":
                removed.append(pkg)
            else:
                return {"status": "failed", "error": result.get("stderr", result.get("error")), "removed": removed}
        return {"status": "success", "operation": "uninstall", "manager": manager, "removed": removed}

    def _list(self, manager: str, cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        cmd = cmds["list"]
        result = self._run(cmd, cwd)
        if result["status"] != "success":
            return result
        try:
            if manager == "pip":
                pkgs = json.loads(result["stdout"])
                packages = [{"name": p["name"], "version": p["version"]} for p in pkgs]
            elif manager == "npm":
                data = json.loads(result["stdout"])
                packages = self._parse_npm_list(data)
            elif manager == "cargo":
                lines = result["stdout"].strip().split("\n")
                packages = [{"name": l.split()[0], "version": l.split()[1]} for l in lines if l and " " in l]
            elif manager == "apt":
                lines = result["stdout"].strip().split("\n")
                packages = [{"name": l.split()[1], "version": l.split()[2]} for l in lines if l.startswith("ii")]
            else:
                packages = [{"raw": result["stdout"]}]
            return {"status": "success", "operation": "list", "manager": manager, "packages": packages}
        except Exception as exc:
            return {"status": "success", "operation": "list", "manager": manager, "packages": [{"raw": result["stdout"]}]}

    def _parse_npm_list(self, data: Dict) -> List[Dict]:
        packages = []
        for name, info in data.get("dependencies", {}).items():
            packages.append({"name": name, "version": info.get("version", "")})
        return packages

    def _show(self, manager: str, packages: List[str], cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if not packages:
            return {"status": "failed", "error": "package required for show"}
        info = {}
        for pkg in packages:
            cmd = cmds["show"] + [pkg]
            result = self._run(cmd, cwd)
            if result["status"] == "success":
                try:
                    info[pkg] = json.loads(result["stdout"])
                except Exception:
                    info[pkg] = {"raw": result["stdout"]}
            else:
                info[pkg] = {"error": result.get("stderr", "unknown")}
        return {"status": "success", "operation": "show", "manager": manager, "info": info}

    def _search(self, manager: str, packages: List[str], cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if not packages:
            return {"status": "failed", "error": "query required for search"}
        query = " ".join(packages)
        cmd = cmds["search"] + [query]
        result = self._run(cmd, cwd)
        if result["status"] != "success":
            return result
        try:
            if manager == "npm":
                return {"status": "success", "operation": "search", "manager": manager, "results": json.loads(result["stdout"])}
        except Exception:
            pass
        return {"status": "success", "operation": "search", "manager": manager, "results": result["stdout"]}

    def _update(self, manager: str, cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if "update" not in cmds:
            return {"status": "failed", "error": f"update not supported for {manager}"}
        result = self._run(cmds["update"], cwd)
        return {"status": result["status"], "operation": "update", "manager": manager, "stdout": result["stdout"], "stderr": result["stderr"]}

    def _audit(self, manager: str, cwd: Optional[str], cmds: Dict) -> Dict[str, Any]:
        if "audit" not in cmds:
            return {"status": "failed", "error": f"audit not supported for {manager}"}
        result = self._run(cmds["audit"], cwd)
        if result["status"] != "success":
            return result
        try:
            return {"status": "success", "operation": "audit", "manager": manager, "results": json.loads(result["stdout"])}
        except Exception:
            return {"status": "success", "operation": "audit", "manager": manager, "results": result["stdout"]}