#!/usr/bin/env python3
"""
HERCULE Sandbox Security Audit
Author: Heeran Paul
License: MIT

Audits sandbox profiles for security misconfigurations.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List, Set

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from security.sandbox.sandbox_manager import SandboxManager, SandboxProfile, SandboxLimits


class SandboxAuditor:
    """Security auditor for sandbox profiles."""
    
    # Paths that should NEVER be accessible
    CRITICAL_DENIED_PATHS = {
        "/etc", "/root", "/home", "/boot", "/sys", "/proc", "/dev",
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "C:\\System Volume Information", "C:\\$Recycle.Bin",
    }
    
    # Paths that should be allowed only with explicit intent
    SENSITIVE_ALLOWED_PATHS = {
        "/tmp", "/var/tmp", "/var/log", "/var/run",
        "C:\\Temp", "C:\\Windows\\Temp",
    }
    
    def __init__(self):
        self.manager = SandboxManager()
        self.findings: List[Dict[str, Any]] = []
    
    def audit_all(self) -> Dict[str, Any]:
        """Run complete audit."""
        self.findings = []
        
        for profile_name in SandboxProfile:
            profile = self.manager.get_profile(profile_name)
            self._audit_profile(profile_name, profile)
        
        # Check for custom profiles
        for name, profile in self.manager._profiles.items():
            if name not in SandboxProfile:
                self._audit_custom_profile(name, profile)
        
        # Global checks
        self._audit_global_config()
        
        return self._generate_report()
    
    def _audit_profile(self, name: SandboxProfile, limits):
        """Audit a built-in profile."""
        prefix = f"profile.{name.value}"
        
        # Check denied paths
        denied = set(limits.denied_paths)
        for critical in self.CRITICAL_DENIED_PATHS:
            if critical not in denied:
                self._add_finding(
                    "HIGH",
                    f"{prefix}.denied_paths",
                    f"Critical path not denied: {critical}",
                    f"Add '{critical}' to denied_paths to prevent access to system directories",
                )
        
        # Check for overly permissive allowed paths
        allowed = set(limits.allowed_paths)
        for sensitive in self.SENSITIVE_ALLOWED_PATHS:
            if sensitive in allowed:
                self._add_finding(
                    "MEDIUM",
                    f"{prefix}.allowed_paths",
                    f"Sensitive path allowed: {sensitive}",
                    f"Only allow sensitive paths when explicitly required",
                )
        
        # Check network settings
        if limits.network_allowed:
            self._add_finding(
                "MEDIUM",
                f"{prefix}.network_allowed",
                "Network access enabled",
                "Ensure network egress is controlled and monitored",
            )
        else:
            self._add_finding(
                "INFO",
                f"{prefix}.network_allowed",
                "Network access disabled (good)",
                "",
            )
        
        # Check resource limits
        self._check_resource_limits(prefix, limits)
        
        # Check denied paths specificity
        for path in limits.denied_paths:
            if path.endswith("*") or path.endswith("/*"):
                self._add_finding(
                    "LOW",
                    f"{prefix}.denied_paths",
                    f"Wildcard in denied path: {path}",
                    "Prefer explicit paths; wildcards may not work as expected",
                )
    
    def _audit_custom_profile(self, name: str, limits):
        """Audit a custom profile."""
        prefix = f"profile.custom.{name}"
        self._add_finding(
            "INFO",
            f"{prefix}",
            f"Custom profile registered: {name}",
            "Ensure custom profiles are reviewed and documented",
        )
        self._audit_profile(SandboxProfile.CUSTOM, limits)
    
    def _check_resource_limits(self, prefix: str, limits):
        """Check resource limits for reasonableness."""
        if limits.max_cpu_time > 300:
            self._add_finding(
                "MEDIUM",
                f"{prefix}.max_cpu_time",
                f"CPU time limit very high: {limits.max_cpu_time}s",
                "Consider lower limits to prevent resource exhaustion",
            )
        
        if limits.max_memory_mb > 2048:
            self._add_finding(
                "MEDIUM",
                f"{prefix}.max_memory_mb",
                f"Memory limit very high: {limits.max_memory_mb}MB",
                "Consider lower limits to prevent OOM",
            )
        
        if limits.max_wall_time > 1800:
            self._add_finding(
                "LOW",
                f"{prefix}.max_wall_time",
                f"Wall time limit very high: {limits.max_wall_time}s",
                "Consider lower limits to prevent hung processes",
            )
        
        if limits.max_processes > 50:
            self._add_finding(
                "MEDIUM",
                f"{prefix}.max_processes",
                f"Process limit very high: {limits.max_processes}",
                "Consider lower limits to prevent fork bombs",
            )
        
        if limits.max_file_size_mb > 1000:
            self._add_finding(
                "LOW",
                f"{prefix}.max_file_size_mb",
                f"File size limit very high: {limits.max_file_size_mb}MB",
                "Consider lower limits to prevent disk exhaustion",
            )
        
        if limits.max_open_files > 256:
            self._add_finding(
                "LOW",
                f"{prefix}.max_open_files",
                f"Open files limit very high: {limits.max_open_files}",
                "Consider lower limits to prevent fd exhaustion",
            )
    
    def _audit_global_config(self):
        """Audit global sandbox configuration."""
        # Check if sandbox is enabled
        manager = SandboxManager()
        if not manager.enabled:
            self._add_finding(
                "HIGH",
                "global.enabled",
                "Sandbox is disabled",
                "Enable sandbox to enforce isolation",
            )
        else:
            self._add_finding(
                "INFO",
                "global.enabled",
                "Sandbox is enabled (good)",
                "",
            )
        
        # Check default profile
        if manager.default_profile == SandboxProfile.STRICT:
            self._add_finding(
                "INFO",
                "global.default_profile",
                "Default profile is STRICT (good)",
                "",
            )
        else:
            self._add_finding(
                "MEDIUM",
                "global.default_profile",
                f"Default profile is {manager.default_profile.value} (not STRICT)",
                "Consider using STRICT as default for defense in depth",
            )
        
        # Check workspace root
        try:
            workspace = manager.workspace_root
            if workspace == Path("/").resolve() or workspace == Path("C:\\").resolve():
                self._add_finding(
                    "HIGH",
                    "global.workspace_root",
                    f"Workspace root is system root: {workspace}",
                    "Set workspace_root to a dedicated directory",
                )
        except Exception:
            pass
    
    def _add_finding(self, severity: str, component: str, message: str, recommendation: str):
        """Add a finding to the audit."""
        self.findings.append({
            "severity": severity,
            "component": component,
            "message": message,
            "recommendation": recommendation,
        })
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate audit report."""
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        sorted_findings = sorted(self.findings, key=lambda f: severity_order.get(f["severity"], 5))
        
        counts = {s: 0 for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]}
        for f in self.findings:
            counts[f["severity"]] += 1
        
        return {
            "summary": {
                "total_findings": len(self.findings),
                "by_severity": counts,
                "profiles_audited": len(SandboxProfile) + len([p for p in self.manager._profiles if p not in SandboxProfile]),
            },
            "findings": sorted_findings,
        }


def main():
    """Run audit and output report."""
    auditor = SandboxAuditor()
    report = auditor.audit_all()
    
    # Print summary
    print("=" * 60)
    print("HERCULE Sandbox Security Audit Report")
    print("=" * 60)
    print(f"Total findings: {report['summary']['total_findings']}")
    for severity, count in report['summary']['by_severity'].items():
        if count:
            print(f"  {severity}: {count}")
    print(f"Profiles audited: {report['summary']['profiles_audited']}")
    print()
    
    # Print findings
    for finding in report["findings"]:
        sev = finding["severity"]
        comp = finding["component"]
        msg = finding["message"]
        rec = finding["recommendation"]
        prefix = {"CRITICAL": "!!! ", "HIGH": "!! ", "MEDIUM": "! ", "LOW": "- ", "INFO": "  "}.get(sev, "  ")
        print(f"{prefix}[{sev}] {comp}: {msg}")
        if rec:
            print(f"      -> {rec}")
    
    # Exit code based on severity
    if report['summary']['by_severity'].get("CRITICAL", 0) > 0:
        return 2
    elif report['summary']['by_severity'].get("HIGH", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())