from __future__ import annotations
"""Kaggle kernel/dataset executor via official CLI (spec §13).

No browser automation. Credential check first; every command surfaces
returncode + tail output. Never assumes the granted accelerator — the
remote job verifies and records it.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache


BOOTSTRAP = '''import json, os, runpy, sys
from pathlib import Path
requested = Path("/kaggle/input/{dataset_slug}")
manifests = list(Path("/kaggle/input").rglob("BUNDLE_MANIFEST.json"))
if (requested / "BUNDLE_MANIFEST.json").is_file():
    bundle = str(requested)
elif manifests:
    bundle = str(manifests[0].parent)
else:
    mounted = sorted(str(p) for p in Path("/kaggle/input").iterdir())
    print("KAGGLE_INPUT_DIRS=" + json.dumps(mounted), flush=True)
    raise FileNotFoundError("uploaded HERCULE bundle manifest is not mounted")
print("HERCULE_BUNDLE_MOUNT=" + bundle, flush=True)
os.environ["HERCULE_BUNDLE"] = bundle
os.environ["HERCULE_REMOTE_JSON"] = {params_json!r}
sys.path.insert(0, bundle)
runpy.run_path(os.path.join(bundle, "tools", "kaggle_trainer", "remote_job.py"),
               run_name="__main__")
'''


def _env(key: str) -> str:
    return os.environ.get(key, "")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(_read_text(path))
    except (OSError, ValueError):
        return {}


def _cli(*args: str, timeout: int = 600) -> Dict[str, Any]:
    env = os.environ.copy()
    # Newer Kaggle CLI OAuth login stores a refreshable token separately,
    # while dataset/kernel API calls still require KAGGLE_API_TOKEN. Bridge
    # the existing authenticated session in memory; never persist or log it.
    if not env.get("KAGGLE_API_TOKEN") and args[:2] != ("auth", "print-access-token"):
        auth = subprocess.run(["kaggle", "auth", "print-access-token"],
                              capture_output=True, text=True, timeout=min(timeout, 300))
        token = (auth.stdout or "").strip()
        if auth.returncode == 0 and token:
            env["KAGGLE_API_TOKEN"] = token
    proc = subprocess.run(["kaggle", *args], capture_output=True,
                          text=True, timeout=timeout, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"returncode": proc.returncode, "output": out,
            "tail": out[-3000:]}


def _path(name: str) -> Path:
    return Path.home() / name


def _kaggle_json() -> Path:
    return _path(".kaggle") / "kaggle.json"


def _credentials_json() -> Path:
    return _path(".kaggle") / "credentials.json"


def _configured_username() -> str:
    """Return the Kaggle account name without exposing credential values."""
    value = _env("KAGGLE_USERNAME").strip()
    if value:
        return value
    for path in (_credentials_json(), _kaggle_json()):
        data = _read_json(path) if path.exists() else {}
        value = str(data.get("username", "") or "").strip()
        if value:
            return value
    return ""


def _print_access_token() -> Dict[str, Any]:
    return _cli("auth", "print-access-token", timeout=300)


def _kaggle_list() -> Dict[str, Any]:
    return _cli("kernels", "list", "--mine", "--page-size", "5", timeout=300)


def is_authenticated() -> Dict[str, Any]:
    """Probe the official Kaggle CLI authentication state.

    Result levels (checked in order):
      AUTHENTICATED / KAGGLE_AUTH_INVALID / KAGGLE_CREDENTIALS_MISSING
    """
    # A. KAGGLE_API_TOKEN environment variable (documented CLI method).
    if _env("KAGGLE_API_TOKEN"):
        tok = _env("KAGGLE_API_TOKEN").strip()
        if tok:
            try:
                res = _print_access_token()
            except Exception:
                return {"status": "KAGGLE_AUTH_INVALID",
                        "via": "KAGGLE_API_TOKEN"}
            if res["returncode"] == 0 and res["output"].strip():
                return {"status": "AUTHENTICATED",
                        "via": "KAGGLE_API_TOKEN"}
            return {"status": "KAGGLE_AUTH_INVALID",
                    "via": "KAGGLE_API_TOKEN"}

    # B. kaggle auth login session (credentials.json / refresh_token).
    # Validate the token directly; listing kernels can fail for reasons
    # unrelated to authentication (for example, API endpoint permissions).
    cfg = _credentials_json()
    if cfg.exists():
        try:
            data = _read_json(cfg)
        except Exception:
            data = {}
        if data.get("username"):
            try:
                res = _print_access_token()
            except Exception:
                return {"status": "KAGGLE_AUTH_INVALID", "via": "kaggle auth login"}
            if res["returncode"] == 0 and res["output"].strip():
                return {"status": "AUTHENTICATED", "via": "kaggle auth login"}
            return {"status": "KAGGLE_AUTH_INVALID", "via": "kaggle auth login"}

    # C. KAGGLE_USERNAME + KAGGLE_KEY (existing env pair).
    user = _env("KAGGLE_USERNAME")
    key = _env("KAGGLE_KEY")
    if user and key:
        try:
            res = _print_access_token()
        except Exception:
            return {"status": "KAGGLE_AUTH_INVALID", "via": "KAGGLE_USERNAME+KAGGLE_KEY"}
        if res["returncode"] == 0 and res["output"].strip():
            return {"status": "AUTHENTICATED", "via": "KAGGLE_USERNAME+KAGGLE_KEY"}
        return {"status": "KAGGLE_AUTH_INVALID", "via": "KAGGLE_USERNAME+KAGGLE_KEY"}

    # D. kaggle.json config file (existing file scheme).
    kjson = _kaggle_json()
    if kjson.exists():
        try:
            data = _read_json(kjson)
        except Exception:
            data = {}
        user = str(data.get("username", "") or "").strip()
        key = str(data.get("key", "") or "").strip()
        if user and key:
            try:
                res = _print_access_token()
            except Exception:
                return {"status": "KAGGLE_AUTH_INVALID", "via": "kaggle.json"}
            if res["returncode"] == 0 and res["output"].strip():
                return {"status": "AUTHENTICATED", "via": "kaggle.json"}
            return {"status": "KAGGLE_AUTH_INVALID", "via": "kaggle.json"}

    return {"status": "KAGGLE_CREDENTIALS_MISSING"}


def creds_ok() -> Dict[str, Any]:
    """Entry point: returns the legacy shape still consumed by the controller."""
    probe = is_authenticated()
    if probe["status"] == "AUTHENTICATED":
        return {"ok": True, "via": probe["via"],
                "username": _configured_username()}
    reason = probe["reason"] if probe.get("reason") else probe["status"]
    return {"ok": False, "reason": reason}


# Keep the existing helpers for the kernel/dataset builders.
def make_kernel_dir(kernel_dir: str, user: str, slug: str, title: str,
                    dataset_slug: str, params: Dict[str, Any],
                    gpu: bool = True) -> str:
    """Generate kernel dir: bootstrap.py + kernel-metadata.json."""
    target = Path(kernel_dir)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "bootstrap.py").write_text(
        BOOTSTRAP.format(dataset_slug=dataset_slug,
                         params_json=json.dumps(params)), encoding="utf-8")
    dataset_sources = [f"{user}/{dataset_slug}"] if dataset_slug else []
    (target / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/{slug}",
        "title": title,
        "code_file": "bootstrap.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "true" if gpu else "false",
        "enable_internet": "false",
        "dataset_sources": dataset_sources,
        "competition_sources": [],
        "kernel_sources": [],
    }, indent=1), encoding="utf-8")
    (target / "REMOTE_PARAMS.json").write_text(
        json.dumps(params, indent=1), encoding="utf-8")
    return str(target)


def make_dataset_dir(bundle_dir: str, dataset_dir: str, user: str,
                     slug: str, title: str) -> str:
    """Copy bundle into a dataset dir + dataset-metadata.json."""
    src, target = Path(bundle_dir), Path(dataset_dir)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src, target)
    (target / "dataset-metadata.json").write_text(json.dumps({
        "title": title,
        "id": f"{user}/{slug}",
        "licenses": [{"name": "other"}],
    }, indent=1), encoding="utf-8")
    return str(target)


def datasets_create(dataset_dir: str) -> Dict[str, Any]:
    res = _cli("datasets", "create", "-p", dataset_dir, "-r", "tar",
               timeout=1200)
    low = (res.get("output", "") or "").lower()
    if res["returncode"] and any(marker in low for marker in (
            "already exists", "already been created", "already exist")):
        return _cli("datasets", "version", "-p", dataset_dir,
                    "-m", "Refresh HERCULE training bundle", "-r", "tar",
                    timeout=1200)
    return res


def kernels_push(kernel_dir: str) -> Dict[str, Any]:
    return _cli("kernels", "push", "-p", kernel_dir, timeout=1200)


def kernels_status(kernel_id: str) -> Dict[str, Any]:
    return _cli("kernels", "status", kernel_id, timeout=120)


def kernels_output(kernel_id: str, dest: str, force: bool = True) -> Dict[str, Any]:
    args = ["kernels", "output", kernel_id, "-p", dest]
    if force:
        args += ["--force"]
    return _cli(*args, timeout=1800)


def kernels_list(mine: bool = True) -> Dict[str, Any]:
    args = ["kernels", "list"] + (["--mine"] if mine else []) + ["--page-size", "5"]
    return _cli(*args, timeout=120)
