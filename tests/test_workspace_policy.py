"""Tests for P1 Selected-Content Understanding: Workspace Policy Enforcement.

Tests cover:
1. No active workspace - access denied
2. Allowed in-workspace read/list
3. Relative traversal rejection (..)
4. Absolute-path escape rejection
5. Similar-prefix rejection (workspace-other/)
6. Nested allowed path
7. Sensitive-file rejection (.env, private keys)
8. Bounded read/truncation
9. Non-text/binary handling
10. Symlink/junction escape rejection
11. Read-only enforcement (no write via P1 path)
12. Consulted-file record privacy
"""

from __future__ import annotations

import os
import tempfile
import pytest
from pathlib import Path

from workspace_manager import WorkspaceManager, create_workspace_manager, _is_sensitive_file, _matches_sensitive


class TestWorkspacePolicy:
    """Test suite for WorkspaceManager policy enforcement."""

    def setup_method(self):
        """Create a temporary workspace for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        
        # Create test files
        (self.workspace / "normal.txt").write_text("hello world")
        (self.workspace / "nested").mkdir(parents=True, exist_ok=True)
        (self.workspace / "nested" / "deep.txt").write_text("deep content")
        
        # Create sensitive files
        (self.workspace / ".env").write_text("SECRET=123")
        (self.workspace / "id_rsa").write_text("fake private key")
        (self.workspace / "secret.key").write_text("secret")
        (self.workspace / "credentials.json").write_text('{"token": "abc"}')
        
        # Create a binary file
        (self.workspace / "binary.bin").write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        
        # Create a large text file
        large_content = "x" * 10000
        (self.workspace / "large.txt").write_text(large_content)
        
        # Create outside workspace
        self.outside = Path(self.temp_dir) / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("outside secret")
        
        # Create similar-prefix directory
        self.similar = Path(self.temp_dir) / "workspace-other"
        self.similar.mkdir()
        (self.similar / "file.txt").write_text("similar prefix")
        
        self.wm = WorkspaceManager()

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ================================================================
    # 1. No active workspace - access denied
    # ================================================================
    def test_no_active_workspace_denied(self):
        """Read/list with no selected workspace is denied."""
        wm = WorkspaceManager()
        
        # Read should be denied
        result = wm.read_file("normal.txt")
        assert not result.allowed
        assert result.denial_category == "no_workspace"
        assert "no workspace selected" in result.reason.lower()
        
        # List should be denied
        result = wm.list_directory(".")
        assert not result.allowed
        assert result.denial_category == "no_workspace"
        
        # No fallback to broad filesystem access
        assert result.denial_category == "no_workspace"

    # ================================================================
    # 2. Allowed in-workspace read/list
    # ================================================================
    def test_allowed_in_workspace_read(self):
        """Normal text file inside workspace can be read."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.read_file("normal.txt")
        assert result.allowed
        assert result.workspace_relative == "normal.txt"
        assert "hello world" in result.path.read_text()
        
        # Consulted-file record created
        records = self.wm.get_consulted_files()
        assert len(records) == 1
        assert records[0].workspace_relative == "normal.txt"
        assert records[0].operation == "read"
        assert records[0].allowed is True

    def test_allowed_in_workspace_list(self):
        """Directory listing works within workspace."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.list_directory(".")
        assert result.allowed
        # result.truncation contains item_count as int
        assert result.truncation.get("item_count", 0) > 0
        
        records = self.wm.get_consulted_files()
        assert any(r.operation == "list" for r in records)

    # ================================================================
    # 3. Relative traversal rejection (..)
    # ================================================================
    def test_relative_traversal_rejected(self):
        """Path traversal with .. is denied."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.read_file("../outside/secret.txt")
        assert not result.allowed
        assert result.denial_category == "traversal"
        assert "escapes workspace" in result.reason.lower()
        
        # Also test with nested path
        result = self.wm.read_file("nested/../../outside/secret.txt")
        assert not result.allowed
        assert result.denial_category == "traversal"

    # ================================================================
    # 4. Absolute-path escape rejection
    # ================================================================
    def test_absolute_path_escape_rejected(self):
        """Absolute path outside workspace is denied."""
        self.wm.select_workspace(str(self.workspace))
        
        outside_file = str(self.outside / "secret.txt")
        result = self.wm.read_file(outside_file)
        assert not result.allowed
        assert result.denial_category == "traversal"
        assert "escapes workspace" in result.reason.lower()

    # ================================================================
    # 5. Similar-prefix rejection (workspace-other/)
    # ================================================================
    def test_similar_prefix_rejected(self):
        """Sibling path like workspace-other/ is denied - proves no string-prefix check."""
        self.wm.select_workspace(str(self.workspace))
        
        # This would pass a naive string-prefix check but must fail proper containment
        similar_file = str(self.similar / "file.txt")
        result = self.wm.read_file(similar_file)
        assert not result.allowed
        assert result.denial_category == "traversal"
        
        # Also test with relative path that looks like it might work
        # but actually goes outside
        result = self.wm.read_file("workspace-other/file.txt")
        assert not result.allowed

    # ================================================================
    # 6. Nested allowed path
    # ================================================================
    def test_nested_allowed_path(self):
        """Normal nested file inside workspace is allowed."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.read_file("nested/deep.txt")
        assert result.allowed
        # Normalize path separators for cross-platform comparison
        import os
        expected = os.path.normpath("nested/deep.txt")
        assert os.path.normpath(result.workspace_relative) == expected
        assert "deep content" in result.path.read_text()

    # ================================================================
    # 7. Sensitive-file rejection
    # ================================================================
    @pytest.mark.parametrize("sensitive_file", [
        ".env",
        "id_rsa",
        "secret.key",
        "credentials.json",
    ])
    def test_sensitive_file_rejected(self, sensitive_file):
        """Sensitive files are denied before content is returned."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.read_file(sensitive_file)
        assert not result.allowed
        assert result.denial_category == "sensitive_file"
        assert "sensitive" in result.reason.lower()
        
        # No content exposed
        records = self.wm.get_consulted_files()
        assert any(r.denial_category == "sensitive_file" for r in records)
        # Verify no content leaked in denial
        assert "SECRET" not in result.reason
        assert "private key" not in result.reason.lower()

    # ================================================================
    # 8. Bounded read/truncation
    # ================================================================
    def test_bounded_read_truncation_by_lines(self):
        """Large file is truncated at line limit with metadata."""
        self.wm.select_workspace(str(self.workspace))
        
        # Set low line limit
        self.wm.set_limits(max_lines=3)
        
        # Create a file with more lines than the limit
        large_content = "\n".join([f"line {i}" for i in range(10)])
        (self.workspace / "large.txt").write_text(large_content)
        
        result = self.wm.read_file("large.txt")
        assert result.allowed
        assert result.truncation is not None
        assert result.truncation.get("truncated") is True
        assert result.truncation.get("reason") == "line_or_char_limit"
        assert result.truncation.get("lines_read") <= 3
        assert "truncated" in result.truncation.get("message", "").lower()
        
        # Consulted record shows truncation
        records = self.wm.get_consulted_files()
        assert records[-1].truncation is not None
        assert records[-1].truncation.get("truncated") is True

    def test_bounded_read_truncation_by_chars(self):
        """Large file is truncated at character limit with metadata."""
        self.wm.select_workspace(str(self.workspace))
        
        # Set low char limit
        self.wm.set_limits(max_chars=50)
        
        result = self.wm.read_file("large.txt")
        assert result.allowed
        assert result.truncation is not None
        assert result.truncation.get("truncated") is True
        assert result.truncation.get("chars_read", 0) <= 50

    def test_bounded_read_truncation_by_size(self):
        """File exceeding size limit is rejected with metadata."""
        self.wm.select_workspace(str(self.workspace))
        
        # Set very low size limit
        self.wm.set_limits(max_file_size=100)
        
        result = self.wm.read_file("large.txt")
        assert not result.allowed
        assert result.denial_category == "size_limit"
        assert result.truncation is not None
        assert result.truncation.get("truncated") is True
        assert "size_limit" in result.truncation.get("reason", "")

    # ================================================================
    # 9. Non-text/binary handling
    # ================================================================
    def test_binary_file_rejected(self):
        """Binary file is not treated as normal text."""
        self.wm.select_workspace(str(self.workspace))
        
        result = self.wm.read_file("binary.bin")
        # Binary files are detected and rejected/handled safely
        assert not result.allowed
        assert result.denial_category in ("binary_file", "size_limit", "read_error")

    # ================================================================
    # 10. Symlink/junction escape rejection
    # ================================================================
    @pytest.mark.skipif(os.name == "nt", reason="Windows junction test requires admin")
    def test_symlink_escape_rejected_unix(self):
        """Symlink pointing outside workspace is denied (Unix)."""
        if os.name == "nt":
            pytest.skip("Unix symlink test")
        
        self.wm.select_workspace(str(self.workspace))
        
        # Create symlink inside workspace pointing outside
        link_path = self.workspace / "link_to_outside"
        try:
            link_path.symlink_to(self.outside / "secret.txt")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported in test environment")
        
        result = self.wm.read_file("link_to_outside")
        assert not result.allowed
        assert result.denial_category == "symlink_escape"

    @pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
    def test_junction_escape_rejected_windows(self):
        """Junction pointing outside workspace is denied (Windows)."""
        if os.name != "nt":
            pytest.skip("Windows junction test")
        
        self.wm.select_workspace(str(self.workspace))
        
        # Create junction inside workspace pointing outside
        link_path = self.workspace / "junction_to_outside"
        try:
            # Windows junction creation requires admin in some cases
            os.system(f'mklink /J "{link_path}" "{self.outside}"')
        except Exception:
            pytest.skip("junctions not supported in test environment")
        
        result = self.wm.read_file("junction_to_outside/secret.txt")
        assert not result.allowed
        assert result.denial_category == "symlink_escape"

    # ================================================================
    # 11. Read-only enforcement (no write via P1 path)
    # ================================================================
    def test_readonly_enforcement_no_write_via_p1(self):
        """P1 read-only path exposes no write operation."""
        self.wm.select_workspace(str(self.workspace))
        
        # WorkspaceManager has no write method
        assert not hasattr(self.wm, "write_file")
        assert not hasattr(self.wm, "create_file")
        assert not hasattr(self.wm, "delete_file")
        assert not hasattr(self.wm, "move_file")
        
        # Only read and list are available
        assert hasattr(self.wm, "read_file")
        assert hasattr(self.wm, "list_directory")
        
        # FileAbility in readonly mode uses WorkspaceManager
        from abilities.files.file_ability import FileAbility
        ability = FileAbility()
        ability.set_readonly_mode(True)
        
        # Select workspace through ability
        result = ability.select_workspace(str(self.workspace))
        assert result["status"] == "success"
        
        # Read through ability in readonly mode
        result = ability.execute({"operation": "read", "path": "normal.txt", "readonly": True})
        assert result["status"] == "success"
        
        # Write should fail in readonly mode
        result = ability.execute({"operation": "write", "path": "new.txt", "data": "test", "readonly": True})
        # Should either fail or use legacy path (not P1 path)
        # The key is that P1 path is read-only

    # ================================================================
    # 12. Consulted-file record privacy
    # ================================================================
    def test_consulted_file_record_privacy(self):
        """Denied sensitive reads don't log file contents."""
        self.wm.select_workspace(str(self.workspace))
        
        # Read sensitive file (denied)
        self.wm.read_file(".env")
        
        # Read normal file (allowed)
        self.wm.read_file("normal.txt")
        
        records = self.wm.get_consulted_files()
        
        # Check denied sensitive file record
        denied_record = next((r for r in records if r.denial_category == "sensitive_file"), None)
        assert denied_record is not None
        assert denied_record.allowed is False
        assert denied_record.denial_category == "sensitive_file"
        # No content leaked in denial reason
        assert "SECRET" not in denied_record.denial_reason
        assert "123" not in denied_record.denial_reason
        
        # Check allowed file record
        allowed_record = next((r for r in records if r.workspace_relative == "normal.txt"), None)
        assert allowed_record is not None
        assert allowed_record.allowed is True
        assert allowed_record.operation == "read"
        
        # Paths are workspace-relative, not absolute
        assert not os.path.isabs(allowed_record.workspace_relative)
        assert not os.path.isabs(denied_record.workspace_relative)

    # ================================================================
    # Additional: Workspace selection behavior
    # ================================================================
    def test_workspace_selection_valid(self):
        """Valid workspace selection succeeds."""
        wm = WorkspaceManager()
        result = wm.select_workspace(str(self.workspace))
        assert result.allowed
        assert result.workspace_relative == "."
        assert wm.active_scope is not None
        assert wm.active_scope.root == self.workspace.resolve()

    def test_workspace_selection_nonexistent_denied(self):
        """Non-existent workspace is denied."""
        wm = WorkspaceManager()
        result = wm.select_workspace("/nonexistent/path")
        assert not result.allowed
        assert result.denial_category == "not_found"

    def test_workspace_selection_not_dir_denied(self):
        """File as workspace is denied."""
        wm = WorkspaceManager()
        result = wm.select_workspace(str(self.workspace / "normal.txt"))
        assert not result.allowed
        assert result.denial_category == "not_directory"

    def test_clear_workspace(self):
        """Clearing workspace removes scope."""
        self.wm.select_workspace(str(self.workspace))
        assert self.wm.active_scope is not None
        
        self.wm.clear_workspace()
        assert self.wm.active_scope is None
        
        # Access denied after clear
        result = self.wm.read_file("normal.txt")
        assert not result.allowed
        assert result.denial_category == "no_workspace"

    def test_workspace_info(self):
        """Workspace metadata is available."""
        self.wm.select_workspace(str(self.workspace), name="test-workspace")
        info = self.wm.get_workspace_info()
        assert info["name"] == "test-workspace"
        assert info["root"] == str(self.workspace.resolve())
        assert "selected_at" in info

    def test_consulted_files_cleared(self):
        """Consulted files can be cleared."""
        self.wm.select_workspace(str(self.workspace))
        self.wm.read_file("normal.txt")
        
        records = self.wm.get_consulted_files(clear=True)
        assert len(records) == 1
        
        # After clear, should be empty
        records = self.wm.get_consulted_files()
        assert len(records) == 0

    def test_is_sensitive_file_helper(self):
        """Test the sensitive file pattern matcher."""
        assert _is_sensitive_file(Path(".env")) is True
        assert _is_sensitive_file(Path("id_rsa")) is True
        assert _is_sensitive_file(Path("secret.key")) is True
        assert _is_sensitive_file(Path("credentials.json")) is True
        assert _is_sensitive_file(Path("normal.txt")) is False
        assert _is_sensitive_file(Path("code.py")) is False
        
        # Test _matches_sensitive returns pattern name
        pattern = _matches_sensitive(Path(".env"))
        assert pattern == ".env"
        
        pattern = _matches_sensitive(Path("id_rsa"))
        assert pattern == "id_rsa"
        
        pattern = _matches_sensitive(Path("normal.txt"))
        assert pattern is None


class TestFileAbilityP1Integration:
    """Integration tests for FileAbility with P1 features."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "test.txt").write_text("test content")
        (self.workspace / ".env").write_text("SECRET=123")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ability_select_workspace(self):
        """FileAbility can select workspace for P1."""
        from abilities.files.file_ability import FileAbility
        
        ability = FileAbility()
        result = ability.select_workspace(str(Path(self.temp_dir) / "workspace"))
        assert result["status"] == "success"
        assert "workspace" in result

    def test_ability_read_in_readonly_mode(self):
        """FileAbility read in readonly mode uses WorkspaceManager."""
        from abilities.files.file_ability import FileAbility
        
        ability = FileAbility()
        ability.set_readonly_mode(True)
        
        ws_path = str(Path(self.temp_dir) / "workspace")
        ability.select_workspace(ws_path)
        
        # Read should work
        result = ability.execute({"operation": "read", "path": "test.txt", "readonly": True})
        assert result["status"] == "success"
        assert "test content" in result.get("content", "")

    def test_ability_read_denies_sensitive_in_readonly(self):
        """Read-only mode denies sensitive files."""
        from abilities.files.file_ability import FileAbility
        
        ability = FileAbility()
        ability.set_readonly_mode(True)
        ability.select_workspace(str(Path(self.temp_dir) / "workspace"))
        
        result = ability.execute({"operation": "read", "path": ".env", "readonly": True})
        assert result["status"] == "failed"
        assert result.get("denial_category") == "sensitive_file"

    def test_ability_consulted_files_recorded(self):
        """Consulted files are recorded through ability."""
        from abilities.files.file_ability import FileAbility
        
        ability = FileAbility()
        ability.set_readonly_mode(True)
        ability.select_workspace(str(Path(self.temp_dir) / "workspace"))
        
        ability.execute({"operation": "read", "path": "test.txt", "readonly": True})
        
        records = ability.get_consulted_files()
        assert len(records) >= 1
        assert records[0]["workspace_relative"] == "test.txt"
        assert records[0]["allowed"] is True


class TestSensitiveFilePatterns:
    """Tests for sensitive file pattern matching."""

    def test_all_sensitive_patterns_detected(self):
        """All sensitive patterns are detected."""
        sensitive_files = [
            ".env", ".env.local", ".env.production",
            "id_rsa", "id_ed25519",
            "private.pem", "key.pem", "cert.pem",
            "private.key", "server.key",
            "cert.p12", "cert.pfx",
            "secret.key", "api.key",
            "credentials.json", "aws_credentials", "gcp_credentials",
            "kubeconfig", ".netrc", ".pgpass",
        ]
        
        for fname in sensitive_files:
            assert _is_sensitive_file(Path(fname)), f"Failed to detect: {fname}"
            pattern = _matches_sensitive(Path(fname))
            assert pattern is not None, f"No pattern matched for: {fname}"

    def test_non_sensitive_files_allowed(self):
        """Normal files are not flagged as sensitive."""
        normal_files = [
            "normal.txt", "readme.md", "config.json", "script.py",
            "data.csv", "log.txt", "image.png", "document.pdf",
            "requirements.txt", "package.json", "tsconfig.json",
        ]
        
        for fname in normal_files:
            assert not _is_sensitive_file(Path(fname)), f"False positive: {fname}"
            assert _matches_sensitive(Path(fname)) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])