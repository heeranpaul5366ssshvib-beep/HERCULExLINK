#!/usr/bin/env python3
"""Build clean hercule_kaggle.zip for Kaggle GPU training."""
import os
import zipfile

ROOT = r"C:\Users\hp\HERCULE"
OUT = r"C:\Users\hp\hercule_kaggle.zip"

SKIP_DIRS = {"__pycache__", ".tmp", "artifacts", "build", "checkpoints",
             "streams", ".git", ".venv", "venv", ".ipynb_checkpoints",
             "node_modules", ".next", "dist"}
SKIP_EXT = {".pyc", ".pyo", ".pyd", ".npz", ".npy", ".pkl"}
SKIP_FILES = {"corpus.jsonl", "corpus_augmented.jsonl", "corpus_final.jsonl",
              "fineweb_100m.txt", "c4_100m.txt"}  # redundant/huge; combined corpus included

added = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".pytest")]
        for f in files:
            if any(f.endswith(e) for e in SKIP_EXT):
                continue
            if f in SKIP_FILES:
                continue
            full = os.path.join(root, f)
            arc = os.path.relpath(full, ROOT).replace(os.sep, "/")
            zf.write(full, "HERCULE/" + arc)
            added += 1
    readme = r"C:\Users\hp\KAGGLE_README.md"
    if os.path.exists(readme):
        zf.write(readme, "KAGGLE_README.md")
        added += 1

size = os.path.getsize(OUT)
print(f"Done: {added} files, {size/1e6:.1f} MB -> {OUT}")
