from __future__ import annotations
"""
HERCULE AI Operating System
Module: Audit Manager
Author: Heeran Paul
License: MIT

Persistent, tamper-evident audit logging with hash chaining.
"""

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class AuditEntry:
    """Single audit log entry with hash chain."""
    index: int
    timestamp: str
    action: str
    actor: str
    resource: str
    outcome: str  # success, failure, error
    details: Dict[str, Any]
    prev_hash: str
    hash: str


class AuditManager:
    """
    Persistent audit manager with hash-chained entries for tamper evidence.
    
    Features:
    - Append-only log file with JSON Lines format
    - Hash chain: each entry includes hash of previous entry
    - Periodic checkpoint hashes for quick verification
    - Configurable retention and rotation
    - Thread-safe concurrent access
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        max_file_size_mb: int = 100,
        max_files: int = 10,
        enable_hash_chain: bool = True,
    ):
        self.log_dir = Path(log_dir or self._default_log_dir())
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.max_files = max_files
        self.enable_hash_chain = enable_hash_chain
        self._lock = threading.RLock()
        self._current_file: Optional[Path] = None
        self._entry_count = 0
        self._last_hash = "0" * 64
        self._initialize()

    def _default_log_dir(self) -> str:
        try:
            from system.paths import user_data_dir
            return str(user_data_dir() / "audit_logs")
        except Exception:
            return str(Path.home() / ".hercule" / "audit_logs")

    def _initialize(self):
        """Initialize or resume from existing log files."""
        existing_files = sorted(self.log_dir.glob("audit_*.jsonl"))
        if existing_files:
            self._current_file = existing_files[-1]
            # Replay last file to rebuild hash chain
            self._replay_file(self._current_file)
        else:
            self._rotate_file()

    def _replay_file(self, file_path: Path):
        """Replay file to rebuild hash chain state."""
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    self._entry_count = entry.get("index", self._entry_count)
                    self._last_hash = entry.get("hash", self._last_hash)
                except json.JSONDecodeError:
                    continue

    def _rotate_file(self):
        """Create new log file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._current_file = self.log_dir / f"audit_{timestamp}.jsonl"
        # Clean old files if needed
        self._cleanup_old_files()

    def _cleanup_old_files(self):
        """Remove old log files beyond max_files."""
        files = sorted(self.log_dir.glob("audit_*.jsonl"), key=lambda f: f.stat().st_mtime)
        while len(files) > self.max_files:
            try:
                files.pop(0).unlink()
            except Exception:
                break

    def _compute_hash(self, entry: AuditEntry) -> str:
        """Compute SHA-256 hash of entry."""
        data = f"{entry.index}|{entry.timestamp}|{entry.action}|{entry.actor}|{entry.resource}|{entry.outcome}|{json.dumps(entry.details, sort_keys=True)}|{entry.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

    def log(
        self,
        action: str,
        actor: str = "system",
        resource: str = "",
        outcome: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """
        Log an audit entry with hash chain.
        
        Args:
            action: Description of action performed
            actor: Who performed the action (user, service, plugin, etc.)
            resource: Resource affected (file, API, capability, etc.)
            outcome: success, failure, or error
            details: Additional structured data
            
        Returns:
            The created AuditEntry
        """
        with self._lock:
            self._entry_count += 1
            timestamp = datetime.now(timezone.utc).isoformat()
            entry = AuditEntry(
                index=self._entry_count,
                timestamp=timestamp,
                action=str(action),
                actor=str(actor),
                resource=str(resource),
                outcome=str(outcome),
                details=details or {},
                prev_hash=self._last_hash,
                hash="",  # computed below
            )
            if self.enable_hash_chain:
                entry.hash = self._compute_hash(entry)
            else:
                entry.hash = "disabled"
            self._last_hash = entry.hash
            
            # Write to file
            self._write_entry(entry)
            
            # Check rotation
            if self._current_file and self._current_file.stat().st_size > self.max_file_size:
                self._rotate_file()
            
            return entry

    def _write_entry(self, entry: AuditEntry):
        """Write entry to current log file."""
        data = asdict(entry)
        with open(self._current_file, 'a') as f:
            f.write(json.dumps(data, separators=(',', ':')) + '\n')

    def history(self, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Get audit history (newest first)."""
        files = sorted(self.log_dir.glob("audit_*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        entries = []
        for file_path in files:
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue
            if len(entries) >= limit + offset:
                break
        # Sort by index descending (newest first)
        entries.sort(key=lambda x: x.get("index", 0), reverse=True)
        return entries[offset:offset + limit]

    def verify_integrity(self, file_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Verify hash chain integrity of log file(s).
        
        Returns:
            Dict with verification results
        """
        files = [file_path] if file_path else sorted(self.log_dir.glob("audit_*.jsonl"))
        results = {
            "verified": True,
            "total_entries": 0,
            "corrupted_entries": [],
            "files_checked": 0,
        }
        
        for fpath in files:
            try:
                with open(fpath, 'r') as f:
                    prev_hash = "0" * 64
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            results["verified"] = False
                            results["corrupted_entries"].append({
                                "file": str(fpath), "line": line_num, "error": "JSON decode error"
                            })
                            continue
                        
                        # Reconstruct entry for hash verification
                        test_entry = AuditEntry(
                            index=entry.get("index", 0),
                            timestamp=entry.get("timestamp", ""),
                            action=entry.get("action", ""),
                            actor=entry.get("actor", ""),
                            resource=entry.get("resource", ""),
                            outcome=entry.get("outcome", ""),
                            details=entry.get("details", {}),
                            prev_hash=entry.get("prev_hash", ""),
                            hash="",
                        )
                        computed = self._compute_hash(test_entry)
                        if self.enable_hash_chain and computed != entry.get("hash", ""):
                            results["verified"] = False
                            results["corrupted_entries"].append({
                                "file": str(fpath), "line": line_num, "index": entry.get("index"),
                                "expected": entry.get("hash"), "computed": computed
                            })
                        if entry.get("prev_hash") != prev_hash:
                            results["verified"] = False
                            results["corrupted_entries"].append({
                                "file": str(fpath), "line": line_num, "index": entry.get("index"),
                                "error": "hash chain broken", "expected_prev": prev_hash, "got": entry.get("prev_hash")
                            })
                        prev_hash = entry.get("hash", "")
                        results["total_entries"] += 1
                    results["files_checked"] += 1
            except Exception as exc:
                results["verified"] = False
                results["corrupted_entries"].append({
                    "file": str(fpath), "error": str(exc)
                })
        
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get audit log statistics."""
        files = list(self.log_dir.glob("audit_*.jsonl"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "log_dir": str(self.log_dir),
            "file_count": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "entry_count": self._entry_count,
            "last_hash": self._last_hash,
            "hash_chain_enabled": self.enable_hash_chain,
        }

    def export(self, output_path: str, since: Optional[str] = None) -> int:
        """Export audit logs to a single file."""
        exported = 0
        with open(output_path, 'w') as out:
            for entry in self.history(limit=1000000):
                if since and entry["timestamp"] < since:
                    break
                out.write(json.dumps(entry) + '\n')
                exported += 1
        return exported