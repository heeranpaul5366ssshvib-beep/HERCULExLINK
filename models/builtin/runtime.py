from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Built-in Inference Runtime (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Managed llama.cpp inference engine. HERCULE spawns its own
``llama-server`` child on a loopback port (never Ollama, never a
user-run server), waits for readiness, and stops it on unload. All
HTTP uses the standard library; metrics (load time, tokens/sec,
latency) are measured, never invented. CPU is the default and only
claim unless a GPU is detected and offload is configured.
"""

import json
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


class RuntimeError_(RuntimeError):
    pass


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


class LlamaRuntime:
    """Owns one llama-server child process + its model load."""

    def __init__(self, threads: int = 0, ctx_size: int = 4096,
                 gpu_layers: int = 0, port: int = 0,
                 timeout_s: float = 120.0):
        self.threads = int(threads or 0)
        self.ctx_size = int(ctx_size or 4096)
        self.gpu_layers = int(gpu_layers or 0)
        self.port = int(port or 0)
        self.timeout_s = float(timeout_s or 120.0)
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._model_path = ""
        self.load_time_s = 0.0
        self.last_tokens_per_sec = 0.0
        self.last_prompt_ms = 0.0
        self.last_gen_ms = 0.0
        self.device = "cpu"

    # --------------------------------------------------
    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def model_path(self) -> str:
        with self._lock:
            return self._model_path

    def _post(self, path: str, payload: Dict[str, Any],
              timeout: Optional[float] = None) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(
                request, timeout=timeout or self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, path: str, timeout: float = 5.0) -> Dict[str, Any]:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}",
                timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # --------------------------------------------------
    def start(self, model_path: str, server_binary: Optional[Path] = None,
              extra_args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Load a GGUF model (spawns the server on first use)."""
        from models.builtin.model_manager import ensure_runtime

        model = Path(str(model_path or ""))
        if not model.is_file():
            raise RuntimeError_(f"model file not found: {model}")
        if model.suffix.lower() != ".gguf":
            raise RuntimeError_(f"not a GGUF model: {model.name}")
        binary = Path(str(server_binary)) if server_binary else ensure_runtime()
        if not binary.is_file():
            raise RuntimeError_("inference binary not found")
        with self._lock:
            if (self._proc is not None and self._proc.poll() is None
                    and self._model_path == str(model)):
                return {"loaded": True, "cached": True, "port": self.port}
            self.stop_locked()
        if self.threads <= 0:
            from models.builtin.config import default_threads

            self.threads = default_threads()
        if self.port <= 0:
            self.port = _free_port()
        args = [str(binary), "-m", str(model), "--port", str(self.port),
                "-c", str(self.ctx_size), "-t", str(self.threads),
                "--no-webui"]
        args = [a for a in args if a]
        if self.gpu_layers > 0:
            args += ["-ngl", str(self.gpu_layers)]
        else:
            args += ["-ngl", "0"]
        args += list(extra_args or [])
        started = time.perf_counter()
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            raise RuntimeError_(f"could not start inference engine: {exc}")
        with self._lock:
            self._proc, self._model_path = proc, str(model)
        try:
            self._await_ready(timeout_s=min(300.0, max(60.0, self.timeout_s * 2)))
        except Exception:
            self.stop()
            raise
        self.load_time_s = round(time.perf_counter() - started, 2)
        self.device = "gpu" if self.gpu_layers > 0 else "cpu"
        return {"loaded": True, "cached": False, "port": self.port,
                "load_time_s": self.load_time_s, "device": self.device,
                "threads": self.threads}

    def _await_ready(self, timeout_s: float = 120.0) -> None:
        deadline = time.perf_counter() + timeout_s
        last_error = ""
        while time.perf_counter() < deadline:
            with self._lock:
                proc = self._proc
            if proc is not None and proc.poll() is not None:
                raise RuntimeError_("inference engine exited during load")
            try:
                health = self._get("/health", timeout=3.0)
                if str(health.get("status", "")).lower() in ("ok", "ready", "") \
                        or "error" not in health:
                    return
            except Exception as exc:
                last_error = str(exc)[:120]
            time.sleep(0.5)
        raise RuntimeError_(f"inference engine not ready: {last_error}")

    def chat(self, messages: List[Dict[str, str]],
             max_tokens: int = 512, temperature: float = 0.7,
             top_p: float = 0.9,
             timeout_s: Optional[float] = None) -> Dict[str, Any]:
        """OpenAI-compatible chat completion with measured metrics."""
        if not self.running:
            raise RuntimeError_("inference engine is not running")
        if not messages:
            raise RuntimeError_("refusing empty messages")
        payload = {"messages": list(messages), "stream": False,
                   "n_predict": int(max_tokens or 512),
                   "temperature": float(temperature),
                   "top_p": float(top_p), "cache_prompt": True}
        started = time.perf_counter()
        try:
            data = self._post("/v1/chat/completions", payload,
                              timeout=timeout_s or self.timeout_s)
        except TimeoutError as exc:
            raise TimeoutError(f"built-in generation timed out: {exc}")
        except Exception as exc:
            raise RuntimeError_(f"built-in generation failed: {exc}")
        total_ms = (time.perf_counter() - started) * 1000.0
        try:
            text = str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            raise RuntimeError_("inference engine returned malformed reply")
        if not text.strip():
            raise RuntimeError_("inference engine returned empty reply")
        usage = data.get("usage") or {}
        timings = data.get("timings") or {}
        prompt_ms = float(timings.get("prompt_ms", 0.0) or 0.0)
        gen_ms = float(timings.get("predicted_ms", 0.0) or 0.0)
        predicted = int(usage.get("completion_tokens",
                                  timings.get("predicted_n", 0)) or 0)
        tokens_per_sec = (predicted / (gen_ms / 1000.0)) if gen_ms > 0 else 0.0
        self.last_prompt_ms = round(prompt_ms, 1)
        self.last_gen_ms = round(gen_ms, 1)
        self.last_tokens_per_sec = round(tokens_per_sec, 1)
        return {"text": text, "prompt_ms": self.last_prompt_ms,
                "gen_ms": self.last_gen_ms,
                "tokens_per_sec": self.last_tokens_per_sec,
                "completion_tokens": predicted,
                "total_ms": round(total_ms, 1)}

    # --------------------------------------------------
    def stop_locked(self) -> None:
        proc, self._proc = self._proc, None
        self._model_path = ""
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self.stop_locked()
        self.load_time_s = 0.0
        return {"stopped": True}
