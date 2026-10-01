import shutil
import os
import pathlib
import json

kernel_dir = 'artifacts/kaggle_full'
if os.path.exists(kernel_dir):
    shutil.rmtree(kernel_dir)

src = 'C:/Users/hp/HERCULE'
dst = kernel_dir

shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
    '*.pyc', '__pycache__', '.git', '.gitignore', 'artifacts', 'evaluation', '*.md', '*.txt',
    'debug_*', 'fix_*', '_*.py', '*.log', '.venv', 'venv', '*.pth', '*.pt',
    'weights*', 'checkpoints*', '*.npz', '*.json.old',
    '*.tmp', '.tmp', 'pytest-base', '*.egg-info', 'dist', 'build',
    '.kaggle', '.cache', '*.tar', '*.tar.gz', '*.zip'
))

print('Source copied')

# Create training entry point
train_code = '''
import sys
import os

sys.path.insert(0, os.getcwd())
os.chdir(os.getcwd())

from models.hercule_lm.train_torch import main
import sys

sys.argv = [
    "train_torch.py",
    "--config", "hercule_lm_nano",
    "--steps", "5000",
    "--batch", "32",
    "--seq-len", "32",
    "--device", "cuda",
    "--amp", "fp16",
    "--checkpoint-root", "/kaggle/working/checkpoints"
]

if __name__ == "__main__":
    main()
'''

pathlib.Path(f'{kernel_dir}/train_kaggle.py').write_text(train_code, encoding='utf-8')

# Update metadata
meta = {
    'id': 'heeranpaul/hercule-nano-5k-training-full-source',
    'title': 'HERCULE NANO 5K Training (full source)',
    'code_file': 'train_kaggle.py',
    'language': 'python',
    'kernel_type': 'script',
    'is_private': 'true',
    'enable_gpu': 'true',
    'enable_internet': 'false',
    'dataset_sources': [],
    'competition_sources': [],
    'kernel_sources': [],
}
pathlib.Path(f'{kernel_dir}/kernel-metadata.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')

print('Full kernel ready')