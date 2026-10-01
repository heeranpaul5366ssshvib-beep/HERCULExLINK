import shutil, os, pathlib, json

# Create directories
os.makedirs('artifacts/kaggle_minimal_final/models/hercule_lm', exist_ok=True)
os.makedirs('artifacts/kaggle_minimal_final/training/data', exist_ok=True)
os.makedirs('artifacts/kaggle_minimal_final/training/tokenizer/hercule-bpe-micro-v1', exist_ok=True)
os.makedirs('artifacts/kaggle_minimal_final/models/hercule_lm/configs', exist_ok=True)

# Copy essential files
shutil.copytree('C:/Users/hp/HERCULE/models/hercule_lm', 'artifacts/kaggle_minimal_final/models/hercule_lm', 
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy('C:/Users/hp/HERCULE/training/data/sources.json', 'artifacts/kaggle_minimal_final/training/data/sources.json')
shutil.copytree('C:/Users/hp/HERCULE/training/tokenizer/hercule-bpe-micro-v1', 'artifacts/kaggle_minimal_final/training/tokenizer/hercule-bpe-micro-v1')
shutil.copy('C:/Users/hp/HERCULE/models/hercule_lm/configs/hercule_lm_micro.json', 'artifacts/kaggle_minimal_final/models/hercule_lm/configs/hercule_lm_micro.json')

# Create train script
train_code = 'import sys\nimport os\nsys.path.insert(0, "/kaggle/working")\nos.chdir("/kaggle/working")\n\nfrom models.hercule_lm.train_torch import main\nimport sys\nsys.argv = [\n    "train_torch.py",\n    "--config", "hercule_lm_micro",\n    "--steps", "10000",\n    "--batch", "32",\n    "--seq-len", "512",\n    "--device", "cuda",\n    "--amp", "fp16",\n    "--checkpoint-root", "/kaggle/working/checkpoints"\n]\nif __name__ == "__main__":\n    main()\n'

pathlib.Path('artifacts/kaggle_minimal_final/train.py').write_text(train_code, encoding='utf-8')

# Create minimal kernel metadata
meta = {
    'id': 'heeranpaul/hercule-micro-10k-final',
    'title': 'HERCULE Micro 10K Training',
    'code_file': 'train.py',
    'language': 'python',
    'kernel_type': 'script',
    'is_private': 'true',
    'enable_gpu': 'true',
    'enable_internet': 'false',
    'dataset_sources': [],
    'competition_sources': [],
    'kernel_sources': [],
}

pathlib.Path('artifacts/kaggle_minimal_final/kernel-metadata.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')

print('Minimal kernel ready')