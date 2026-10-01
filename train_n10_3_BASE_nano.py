import json
import time
import numpy as np
import sys, os
from pathlib import Path
sys.path.insert(0, '.')

os.environ['PYTHONUNBUFFERED'] = '1'

from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.data import make_batches

print('Loading N10.2 tokenizer...', flush=True)
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
print(f'Tokenizer: {tokenizer.vocab_size} vocab, {len(tokenizer.merges)} merges', flush=True)

print('Loading N10.2 fixed corpus...', flush=True)
with open('training/data/fixed/fixed_corpus.txt', 'r') as f:
    corpus_text = f.read()
corpus_ids = tokenizer.encode(corpus_text)
print(f'Corpus tokens: {len(corpus_ids)}', flush=True)

split_idx = int(len(corpus_ids) * 0.9)
train_ids = corpus_ids[:split_idx]
val_ids = corpus_ids[split_idx:]
print(f'Train: {len(train_ids)}, Val: {len(val_ids)}', flush=True)

seq_len = 32
micro_batch = 8
train_batches = make_batches(train_ids, seq_len, micro_batch, seed=42)
val_batches = make_batches(val_ids, seq_len, max(1, micro_batch // 2), seed=43)
print(f'Train batches: {len(train_batches)}, Val batches: {len(val_batches)}', flush=True)

# Create new model with N10.2 tokenizer vocab size
config = HerculeLMConfig.from_preset('HERCULE-NANO')
# Update vocab_size to match N10.2 tokenizer
config.vocab_size = tokenizer.vocab_size
print(f'Config vocab_size: {config.vocab_size}', flush=True)

model = HerculeLM(config, seed=42)
print(f'Model params: {model.parameter_count()}', flush=True)

# Training setup
lr = 0.0003
warmup = 50
total_steps = 5000
grad_clip = 1.0
accum_steps = 1

def cosine_lr(step, total, base, warmup=50):
    if step < warmup:
        return base * max(0.05, (step + 1) / max(1, warmup))
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base * 0.5 * (1.0 + np.cos(np.pi * progress))

# Output directory
import os
os.makedirs('training/checkpoints/n10_3_BASE_nano', exist_ok=True)
ckpt_root = Path('training/checkpoints/n10_3_BASE_nano')

# Training state
start_step = 0
tokens_seen = 0
micro_index = 0
accum_grads = None
accum_loss, accum_count = 0.0, 0

eval_every = 500
ckpt_every = 1000

def evaluate(model, batches, max_batches=8):
    losses = []
    for xs, ys in batches[:max_batches]:
        logits, cache = model.forward(xs)
        loss, _ = model.loss_and_backward(logits, cache, ys)
        losses.append(loss)
    return float(sum(losses) / max(1, len(losses)))

# Save initial checkpoint
run_manifest = {
    "run_id": "n10_3_BASE_nano",
    "config": config.as_dict(),
    "seed": 42,
    "optimizer": "adamw", "scheduler": "cosine", "lr": lr,
    "batch": micro_batch, "seq_len": seq_len, "steps": total_steps,
    "device": "cpu", "backend": "numpy", "dtype": "float32",
}

# Save manifests
def save_checkpoint(step):
    target = ckpt_root / f"step_{step:08d}"
    train_state = {"step": step, "lr": lr, "loss": 0.0, "grad_norm": 0.0, "tokens_seen": tokens_seen}
    ckpt.save_checkpoint(str(target), model, tokenizer.manifest(), 
                         {"dataset_hash": "n10.2-fixed"}, train_state, run_manifest)
    print(f'Saved checkpoint step {step}')

print('Starting training...', flush=True)
total_target_steps = start_step + total_steps

try:
    for step in range(start_step, total_target_steps):
        lr_current = cosine_lr(step, total_target_steps, lr)
        
        t0 = time.perf_counter()
        
        for _ in range(accum_steps):
            xs, ys = train_batches[micro_index % len(train_batches)]
            micro_index += 1
            
            logits, cache = model.forward(xs)
            loss, grads = model.loss_and_backward(logits, cache, ys)
            
            if not np.isfinite(loss):
                print(f'Non-finite loss at step {step}: {loss}')
                raise SystemExit(1)
            
            if accum_grads is None:
                accum_grads = {k: v.copy() for k, v in grads.items()}
            else:
                for key in accum_grads:
                    accum_grads[key] += grads[key]
            accum_loss += float(loss)
            accum_count += 1
            tokens_seen += int(xs.size)
        
        mean_loss = accum_loss / max(1, accum_count)
        for key in accum_grads:
            accum_grads[key] /= max(1, accum_count)
        gnorm = model.clip_grads(accum_grads, grad_clip)
        model.adamw_step(accum_grads, lr_current)
        accum_grads, accum_loss, accum_count = None, 0.0, 0
        
        dt = time.perf_counter() - t0
        eff_tokens = micro_batch * seq_len * accum_steps
        
        if (step + 1) % 100 == 0:
            print(f'step={step+1}/{total_target_steps} loss={mean_loss:.4f} lr={lr_current:.2e} gnorm={gnorm:.2f} {dt*1000:.0f}ms {eff_tokens/max(dt,1e-6):.0f}tok/s', flush=True)
        
        if (step + 1) % eval_every == 0:
            val_loss = evaluate(model, val_batches)
            print(f'  valid loss={val_loss:.4f}', flush=True)
        
        if (step + 1) % ckpt_every == 0:
            save_checkpoint(step + 1)
            
except KeyboardInterrupt:
    print('Interrupted')
    save_checkpoint(step + 1)

save_checkpoint(step + 1)
print('Training complete')