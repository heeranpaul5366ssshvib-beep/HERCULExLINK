#!/usr/bin/env python3
"""
HERCULE Model Registry CLI

Manage local GGUF models: list, install, remove, set default, download.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.builtin.model_manager import (
    list_installed,
    find_model,
    default_model_id,
    select_default,
    remove_model,
    download_model,
    ensure_runtime,
    KNOWN_MODELS,
    models_root,
    ModelStoreError,
)


def format_model_list(models: List[dict], default_id: str) -> str:
    """Format model list for display."""
    if not models:
        return "No models installed."
    
    lines = []
    for m in models:
        marker = " * " if m.get("id") == default_id else "   "
        source = "bundled" if not m.get("writable", True) else "installed"
        size_mb = m.get("size", 0) / (1024 * 1024)
        info = f"{marker}{m['id']:<30} {size_mb:>6.1f} MB  [{source}]"
        if "display_name" in m:
            info += f"  ({m['display_name']})"
        if "quant" in m:
            info += f"  {m['quant']}"
        if "context" in m:
            info += f"  ctx:{m['context']}"
        lines.append(info)
    return "\n".join(lines)


def cmd_list(args):
    """List installed and available models."""
    models = list_installed()
    default_id = default_model_id()
    print("Installed models:")
    print(format_model_list(models, default_id))
    
    print("\nAvailable for download:")
    for m in KNOWN_MODELS:
        installed = any(mm.get("id") == m["id"] for mm in models)
        status = "[installed]" if installed else "[available]"
        print(f"  {m['id']:<30} {m.get('display_name', '')}  {status}")


def cmd_install(args):
    """Install a model by ID."""
    try:
        result = download_model(args.model_id)
        if result.get("cached"):
            print(f"Model '{args.model_id}' already installed: {result['path']}")
        else:
            size_mb = result.get("size", 0) / (1024 * 1024)
            print(f"Downloaded '{args.model_id}' ({size_mb:.1f} MB) to {result['path']}")
    except ModelStoreError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_remove(args):
    """Remove an installed model."""
    try:
        result = remove_model(args.model_id)
        print(f"Removed '{result['removed']}' from {result['path']}")
    except ModelStoreError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_default(args):
    """Set or show default model."""
    if args.model_id:
        try:
            result = select_default(args.model_id)
            print(f"Default model set to '{result}'")
        except ModelStoreError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        default = default_model_id()
        if default:
            print(f"Default model: {default}")
        else:
            print("No default model set.")
    return 0


def cmd_info(args):
    """Show detailed info about a model."""
    meta = find_model(args.model_id)
    if not meta:
        print(f"Model '{args.model_id}' not found.", file=sys.stderr)
        return 1
    print(json.dumps(meta, indent=2))
    return 0


def cmd_runtime(args):
    """Ensure llama-server runtime is available."""
    try:
        path = ensure_runtime()
        print(f"Runtime ready: {path}")
    except ModelStoreError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_catalog(args):
    """Show known models catalog."""
    for m in KNOWN_MODELS:
        print(f"  {m['id']:<30} {m.get('display_name', '')}")
        print(f"      size: {m['size'] / (1024*1024):.1f} MB  quant: {m['quant']}  ctx: {m['context']}")
        print(f"      license: {m['license']}  source: {m['source']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="hercule-model",
        description="HERCULE Model Registry - manage local GGUF models",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list
    subparsers.add_parser("list", help="List installed and available models")
    
    # install
    p_install = subparsers.add_parser("install", help="Download and install a model")
    p_install.add_argument("model_id", help="Model ID to install (e.g., qwen2.5-1.5b-q4)")
    
    # remove
    p_remove = subparsers.add_parser("remove", help="Remove an installed model")
    p_remove.add_argument("model_id", help="Model ID to remove")
    
    # default
    p_default = subparsers.add_parser("default", help="Set or show default model")
    p_default.add_argument("model_id", nargs="?", help="Model ID to set as default")
    
    # info
    p_info = subparsers.add_parser("info", help="Show model details")
    p_info.add_argument("model_id", help="Model ID to inspect")
    
    # runtime
    subparsers.add_parser("runtime", help="Ensure llama-server runtime is available")
    
    # catalog
    subparsers.add_parser("catalog", help="Show known models catalog")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "install":
        return cmd_install(args)
    elif args.command == "remove":
        return cmd_remove(args)
    elif args.command == "default":
        return cmd_default(args)
    elif args.command == "info":
        return cmd_info(args)
    elif args.command == "runtime":
        return cmd_runtime(args)
    elif args.command == "catalog":
        cmd_catalog(args)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())