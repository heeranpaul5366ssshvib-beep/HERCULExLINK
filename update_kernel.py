import pathlib, json, shutil, os

kernel_dir = 'artifacts/kaggle_micro_v6'

# Create script.py
script_content = '''import sys
import os
import shutil

src = "/kaggle/src"
dst = "/kaggle/working"

print("=== SETUP ===")
print("Copying from", src, "to", dst)

if os.path.exists(src):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        try:
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
            print(f"Copied: {item}")
        except Exception as e:
            print(f"Copy error for {item}: {e}")

print("Copied files to working directory")
os.chdir("/kaggle/working")
print("Changed CWD to:", os.getcwd())
print("Contents:", os.listdir("."))

sys.path.insert(0, "/kaggle/working")

from models.hercule_lm.train_torch import main
import sys

sys.argv = [
    "train_torch.py",
    "--config", "hercule_lm_micro",
    "--steps", "10000",
    "--batch", "32",
    "--seq-len", "512",
    "--device", "cuda",
    "--amp", "fp16",
    "--checkpoint-root", "/kaggle/working/checkpoints"
]

if __name__ == "__main__":
    main()
'''

pathlib.Path('artifacts/kaggle_micro_v6/script.py').write_text(script_content, encoding="utf-8")

# Update metadata
meta = {
    "id": "heeranpaul/hercule-micro-10k-training-v8",
    "title": "HERCULE Micro 10K Training v8",
    "code_file": "script.py",
    "language": "python",
    "kernel_type": "script",
    "is_private": "true",
    "enable_gpu": "true",
    "enable_internet": "true",
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": [],
}

pathlib.Path("artifacts/kaggle_micro_v6/kernel-metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

print("Updated script.py and metadata")