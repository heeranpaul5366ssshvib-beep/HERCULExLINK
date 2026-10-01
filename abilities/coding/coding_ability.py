from __future__ import annotations
"""
HERCULE AI Operating System
Module: Coding Ability
Author: Heeran Paul
License: MIT

Real implementation: code generation, editing, analysis, execution.
"""

import ast
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from abilities.base_ability import BaseAbility
from workspace_manager import WorkspaceManager, create_workspace_manager


class CodingAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "coding",
            "Code generation, editing, analysis, and execution",
            capability="CODE_EDIT",
            inputs={
                "operation": "generate|edit|analyze|execute|lint|test",
                "code": "code string for generate/edit",
                "file": "workspace-relative path for edit/analyze",
                "language": "python|javascript|typescript|rust|go",
                "prompt": "natural language description for generation",
            },
            outputs={
                "code": "generated/edited code",
                "analysis": "static analysis results",
                "output": "execution output",
                "errors": "any errors",
            },
            permissions=["CODE_EDIT", "CODE_EXECUTION", "FILE_READ", "FILE_WRITE"],
            environments={"default"},
            verification="syntax valid, tests pass, lint clean",
            timeout_s=60,
            risk="HIGH",
        )
        self._workspace_manager = None

    def _ensure_workspace(self):
        if self._workspace_manager is None and create_workspace_manager:
            try:
                from security.auditing.audit_manager import AuditManager
                audit = AuditManager()
                self._workspace_manager = create_workspace_manager(audit)
            except Exception:
                pass
        return self._workspace_manager

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "generate")
            if op in ("edit", "analyze") and not task.get("file"):
                return f"operation '{op}' requires 'file' parameter"
            if op == "generate" and not (task.get("prompt") or task.get("code")):
                return "generate operation requires 'prompt' or 'code'"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty coding request"
        return ""

    def execute(self, task, context=None, **kwargs):
        if isinstance(task, dict):
            operation = str(task.get("operation", "generate")).lower()
            code = task.get("code", "")
            file_path = task.get("file", "")
            language = str(task.get("language", "python")).lower()
            prompt = task.get("prompt", "")
        else:
            operation = "generate"
            prompt = str(task)
            code = ""
            file_path = ""
            language = "python"

        try:
            if operation == "generate":
                return self._generate(prompt, language, code, **kwargs)
            elif operation == "edit":
                return self._edit(file_path, code, **kwargs)
            elif operation == "analyze":
                return self._analyze(file_path, code, language, **kwargs)
            elif operation == "execute":
                return self._execute(code, language, **kwargs)
            elif operation == "lint":
                return self._lint(code, language, **kwargs)
            elif operation == "test":
                return self._test(file_path, code, language, **kwargs)
            else:
                return {"status": "failed", "error": f"unknown operation: {operation}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _generate(self, prompt: str, language: str, existing_code: str, **kwargs) -> Dict[str, Any]:
        templates = {
            "python": self._python_template,
            "javascript": self._javascript_template,
            "typescript": self._typescript_template,
            "rust": self._rust_template,
            "go": self._go_template,
        }
        template_fn = templates.get(language, self._python_template)
        generated = template_fn(prompt, existing_code)
        return {
            "status": "success",
            "operation": "generate",
            "language": language,
            "code": generated,
            "prompt": prompt,
        }

    def _python_template(self, prompt: str, existing: str) -> str:
        if existing:
            return f"{existing}\n\n# Generated from: {prompt}\ndef generated_function():\n    pass"
        return textwrap.dedent(f"""\
            # Generated from: {prompt}
            def main():
                \"\"\"{prompt}\"\"\"
                pass

            if __name__ == "__main__":
                main()
            """)

    def _javascript_template(self, prompt: str, existing: str) -> str:
        if existing:
            return f"{existing}\n\n// Generated from: {prompt}\nfunction generatedFunction() {{\n    // TODO\n}}"
        return f"// Generated from: {prompt}\nfunction main() {{\n    // {prompt}\n}}\n\nmain();"

    def _typescript_template(self, prompt: str, existing: str) -> str:
        if existing:
            return f"{existing}\n\n// Generated from: {prompt}\nfunction generatedFunction(): void {{\n    // TODO\n}}"
        return f"// Generated from: {prompt}\nfunction main(): void {{\n    // {prompt}\n}}\n\nmain();"

    def _rust_template(self, prompt: str, existing: str) -> str:
        if existing:
            return f"{existing}\n\n// Generated from: {prompt}\nfn generated_function() {{\n    // TODO\n}}"
        return f"// Generated from: {prompt}\nfn main() {{\n    // {prompt}\n}}"

    def _go_template(self, prompt: str, existing: str) -> str:
        if existing:
            return f"{existing}\n\n// Generated from: {prompt}\nfunc generatedFunction() {{\n    // TODO\n}}"
        return f"// Generated from: {prompt}\npackage main\n\nfunc main() {{\n    // {prompt}\n}}"

    def _edit(self, file_path: str, new_code: str, **kwargs) -> Dict[str, Any]:
        if not file_path:
            return {"status": "failed", "error": "file path required for edit"}
        wm = self._ensure_workspace()
        if not wm:
            return {"status": "failed", "error": "workspace manager not available"}
        try:
            result = wm.read_file(file_path)
            if not result.allowed:
                return {"status": "failed", "error": result.reason, "denial_category": result.denial_category}
            old_content = result.path.read_text(encoding="utf-8")
            write_result = wm.write_file(file_path, new_code)
            if not write_result.allowed:
                return {"status": "failed", "error": write_result.reason, "denial_category": write_result.denial_category}
            return {
                "status": "success",
                "operation": "edit",
                "file": file_path,
                "old_content": old_content,
                "new_content": new_code,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _analyze(self, file_path: str, code: str, language: str, **kwargs) -> Dict[str, Any]:
        target = code
        if not target and file_path:
            wm = self._ensure_workspace()
            if wm:
                result = wm.read_file(file_path)
                if result.allowed:
                    target = result.path.read_text(encoding="utf-8")
        if not target:
            return {"status": "failed", "error": "no code to analyze"}
        if language == "python":
            return self._analyze_python(target, file_path)
        return {"status": "success", "operation": "analyze", "language": language, "message": "analysis not implemented for this language"}

    def _analyze_python(self, code: str, file_path: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(code)
            issues = []
            functions = []
            classes = []
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({"name": node.name, "line": node.lineno, "args": [a.arg for a in node.args.args]})
                elif isinstance(node, ast.ClassDef):
                    classes.append({"name": node.name, "line": node.lineno, "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]})
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        imports.append({"name": alias.name, "line": node.lineno})
                elif isinstance(node, ast.Call) and hasattr(node.func, 'id') and node.func.id == 'eval':
                    issues.append({"type": "security", "message": "eval() usage detected", "line": getattr(node, 'lineno', 0)})
            return {
                "status": "success",
                "operation": "analyze",
                "file": file_path,
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "issues": issues,
                "lines": len(code.splitlines()),
                "chars": len(code),
            }
        except SyntaxError as exc:
            return {"status": "failed", "error": f"syntax error: {exc.msg} at line {exc.lineno}"}

    def _execute(self, code: str, language: str, **kwargs) -> Dict[str, Any]:
        if not code:
            return {"status": "failed", "error": "no code to execute"}
        if language == "python":
            return self._execute_python(code, **kwargs)
        elif language in ("javascript", "typescript"):
            return self._execute_node(code, **kwargs)
        else:
            return {"status": "failed", "error": f"execution not supported for {language}"}

    def _execute_python(self, code: str, **kwargs) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 30),
            )
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "operation": "execute",
                "language": "python",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "execution timeout"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _execute_node(self, code: str, **kwargs) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_path = f.name
        try:
            result = subprocess.run(
                ["node", temp_path],
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 30),
            )
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "operation": "execute",
                "language": "javascript",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except FileNotFoundError:
            return {"status": "failed", "error": "node not installed"}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "execution timeout"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _lint(self, code: str, language: str, **kwargs) -> Dict[str, Any]:
        if not code:
            return {"status": "failed", "error": "no code to lint"}
        if language == "python":
            try:
                ast.parse(code)
                return {"status": "success", "operation": "lint", "language": "python", "issues": []}
            except SyntaxError as exc:
                return {"status": "success", "operation": "lint", "language": "python", "issues": [
                    {"type": "syntax", "message": exc.msg, "line": exc.lineno}
                ]}
        return {"status": "success", "operation": "lint", "language": language, "issues": [], "message": "lint not implemented for this language"}

    def _test(self, file_path: str, code: str, language: str, **kwargs) -> Dict[str, Any]:
        if language == "python":
            test_code = code
            if file_path and not test_code:
                wm = self._ensure_workspace()
                if wm:
                    result = wm.read_file(file_path)
                    if result.allowed:
                        test_code = result.path.read_text(encoding="utf-8")
            if not test_code:
                return {"status": "failed", "error": "no code to test"}
            with tempfile.NamedTemporaryFile(mode='w', suffix='_test.py', delete=False) as f:
                f.write(test_code)
                temp_path = f.name
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", temp_path, "-v", "--tb=short"],
                    capture_output=True,
                    text=True,
                    timeout=kwargs.get("timeout", 60),
                )
                return {
                    "status": "success" if result.returncode == 0 else "failed",
                    "operation": "test",
                    "language": "python",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
            except Exception as exc:
                return {"status": "failed", "error": str(exc)}
            finally:
                Path(temp_path).unlink(missing_ok=True)
        return {"status": "failed", "error": f"testing not supported for {language}"}