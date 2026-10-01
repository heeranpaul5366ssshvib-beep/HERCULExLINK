from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Built-in Model Store (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Local model file management (NOT an inference manager — inference
lives in runtime.py/provider.py). Layout (user data only, never
Program Files)::

    %LOCALAPPDATA%\\HERCULE\\models\\
        gguf\\*.gguf            downloaded/installed weights
        runtime\\llama-server*  managed inference binary
        default.txt             selected default model id (optional)

Bundled weights (Mode A), when present, are read from the packaged
resources directory; downloads (Mode B) land in user data. No API
keys; plain HTTPS downloads with size validation.
"""

import os
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNTIME_ZIP_URL = ("https://github.com/ggerganov/llama.cpp/releases/download/"
                   "b10927/llama-b10927-bin-win-cpu-x64.zip")
RUNTIME_ZIP_NAME = "llama-b10927-bin-win-cpu-x64.zip"
SERVER_CANDIDATES = ("llama-server.exe", "llama-server")

# Curated small GGUF catalog (metadata only — nothing downloads itself).
# Licenses verified for local use; weights are never copied into the
# repository (user-data download only, never redistributed by us).
KNOWN_MODELS: List[Dict[str, Any]] = [
    {"id": "qwen2.5-0.5b-q4",
     "repo": "bartowski/Qwen2.5-0.5B-Instruct-GGUF",
     "file": "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
     "size": 397000000, "quant": "Q4_K_M", "context": 32768,
     "family": "Qwen2.5", "parameters": "0.5B",
     "license": "Apache-2.0", "publisher": "Qwen (via bartowski GGUF)",
     "source": "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF",
     "display_name": "Qwen2.5 0.5B Instruct (lightweight)",
     "recommended_modes": ["LIGHT"],
     "capabilities": ["chat", "reasoning"]},
    {"id": "qwen2.5-1.5b-q4",
     "repo": "bartowski/Qwen2.5-1.5B-Instruct-GGUF",
     "file": "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
     "size": 1000000000, "quant": "Q4_K_M", "context": 32768,
     "family": "Qwen2.5", "parameters": "1.5B",
     "license": "Apache-2.0", "publisher": "Qwen (via bartowski GGUF)",
     "source": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF",
     "display_name": "Qwen2.5 1.5B Instruct (primary local)",
     "recommended_modes": ["STANDARD", "DEEP"],
     "capabilities": ["chat", "reasoning"]},
]


class ModelStoreError(RuntimeError):
    pass


def models_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    if os.name == "nt" and local:
        base = Path(local) / "HERCULE" / "models"
    else:
        base = Path.home() / ".hercule" / "models"
    base.mkdir(parents=True, exist_ok=True)
    (base / "gguf").mkdir(parents=True, exist_ok=True)
    (base / "runtime").mkdir(parents=True, exist_ok=True)
    return base


def bundled_models_dir() -> Path:
    """Read-only packaged weights (Mode A); may not exist (Mode B)."""
    import sys

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return Path(meipass) / "models"
    here = Path(__file__).resolve()
    return here.parent.parent.parent / "models"


def _gguf_meta(path: Path) -> Dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    quant = "unknown"
    name = path.name
    for tag in ("Q4_K_M", "Q4_0", "Q5_K_M", "Q8_0", "F16", "Q3_K_M"):
        if tag.lower().replace("_", "") in name.lower().replace("_", "") or tag in name:
            quant = tag
            break
    return {"id": path.stem, "path": str(path), "size": size,
            "format": "GGUF", "quant": quant}


def _catalog_meta(path: Path) -> Dict[str, Any]:
    """Attach curated catalog metadata when a file matches a known entry."""
    for entry in KNOWN_MODELS:
        if path.name == entry.get("file"):
            return {"catalog_id": entry["id"],
                    "display_name": entry.get("display_name", ""),
                    "family": entry.get("family", ""),
                    "parameters": entry.get("parameters", ""),
                    "quant": entry.get("quant", ""),
                    "context": entry.get("context", 0),
                    "license": entry.get("license", ""),
                    "publisher": entry.get("publisher", ""),
                    "source": entry.get("source", ""),
                    "recommended_modes": list(entry.get("recommended_modes", [])),
                    "capabilities": list(entry.get("capabilities", []))}
    return {}


def list_installed() -> List[Dict[str, Any]]:
    """Installed GGUF weights: user data first, then bundled (read-only)."""
    found: List[Dict[str, Any]] = []
    seen = set()
    for directory, writable in ((models_root() / "gguf", True),
                                (bundled_models_dir(), False)):
        try:
            files = sorted(directory.glob("*.gguf"))
        except OSError:
            continue
        for path in files:
            if path.name in seen:
                continue
            seen.add(path.name)
            meta = _gguf_meta(path)
            meta.update(_catalog_meta(path))
            meta["writable"] = writable
            found.append(meta)
    return found


def find_model(path_or_id: str) -> Optional[Dict[str, Any]]:
    wanted = str(path_or_id or "").strip()
    if not wanted:
        return None
    direct = Path(wanted)
    if direct.is_file() and direct.suffix.lower() == ".gguf":
        meta = _gguf_meta(direct)
        meta["writable"] = False
        return meta
    for meta in list_installed():
        if meta["id"] == wanted or Path(meta["path"]).name == wanted:
            return meta
    return None


def default_model_id() -> str:
    try:
        text = (models_root() / "default.txt").read_text(
            encoding="utf-8").strip()
        if text:
            return text
    except OSError:
        pass
    installed = list_installed()
    return installed[0]["id"] if installed else ""


def select_default(model_id: str) -> str:
    meta = find_model(model_id)
    if meta is None:
        raise ModelStoreError(f"model not installed: {model_id!r}")
    (models_root() / "default.txt").write_text(meta["id"], encoding="utf-8")
    return meta["id"]


def remove_model(model_id: str) -> Dict[str, Any]:
    meta = find_model(model_id)
    if meta is None:
        raise ModelStoreError(f"model not installed: {model_id!r}")
    if not meta.get("writable"):
        raise ModelStoreError("bundled models cannot be removed")
    Path(meta["path"]).unlink()
    return {"removed": meta["id"], "path": meta["path"]}


def download_file(url: str, target: Path, expected_min_bytes: int = 1024,
                  timeout_s: float = 600.0) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "HERCULE"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, \
                open(tmp, "wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 256)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ModelStoreError(f"download failed: {exc}")
    try:
        size = tmp.stat().st_size
    except OSError:
        size = 0
    if size < expected_min_bytes:
        tmp.unlink(missing_ok=True)
        raise ModelStoreError(f"download too small ({size} bytes): {url}")
    tmp.replace(target)
    return target


def download_model(model_id: str) -> Dict[str, Any]:
    known = next((m for m in KNOWN_MODELS if m["id"] == model_id), None)
    if known is None:
        raise ModelStoreError(f"unknown model {model_id!r} "
                              f"(known: {[m['id'] for m in KNOWN_MODELS]})")
    url = (f"https://huggingface.co/{known['repo']}/resolve/main/"
           f"{known['file']}")
    target = models_root() / "gguf" / known["file"]
    if target.exists() and target.stat().st_size > known["size"] // 2:
        return {"id": known["id"], "path": str(target), "cached": True,
                "size": target.stat().st_size}
    download_file(url, target, expected_min_bytes=known["size"] // 2)
    return {"id": known["id"], "path": str(target), "cached": False,
            "size": target.stat().st_size}


def runtime_dir() -> Path:
    directory = models_root() / "runtime"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def find_server_binary() -> Optional[Path]:
    for directory in (runtime_dir(), bundled_models_dir() / "runtime"):
        for name in SERVER_CANDIDATES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def ensure_runtime() -> Path:
    """Managed llama-server binary (downloads once into user data)."""
    found = find_server_binary()
    if found is not None:
        return found
    directory = runtime_dir()
    archive = directory / RUNTIME_ZIP_NAME
    if not archive.exists():
        download_file(RUNTIME_ZIP_URL, archive, expected_min_bytes=1000000)
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if not names:
                raise ModelStoreError("runtime archive is empty")
            bundle.extractall(directory)
    except zipfile.BadZipFile as exc:
        raise ModelStoreError(f"runtime archive corrupt: {exc}")
    found = find_server_binary()
    if found is None:
        # Binary may sit one level down (build/<config>/bin layout).
        for candidate in directory.rglob("llama-server.exe"):
            return candidate
        raise ModelStoreError("llama-server not found after extract")
    return found
