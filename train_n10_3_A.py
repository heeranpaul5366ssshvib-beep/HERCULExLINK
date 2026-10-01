import json
import time
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.data import make_batches

# Load N10.2 tokenizer
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
print('Tokenizer:', tokenizer.vocab_size, 'vocab', len(tokenizer.merges), 'merges', tokenizer.checksum())

# Load N10.2 fixed corpus
with open('training/data/fixed/fixed_corpus.txt', 'r') as f:
    corpus_text = f.read()
print('Corpus length:', len(corpus_text), 'chars')

# Encode corpus
corpus_ids = tokenizer.encode(corpus_text)
print('Corpus tokens:', len(corpus_ids))

# Split train/val (90/10)
split_idx = int(len(corpus_ids) * 0.9)
train_ids = corpus_ids[:split_idx]
val_ids = corpus_ids[split_idx:]
print('Train tokens:', len(train_ids), 'Val tokens:', len(val_ids))

# Create batches
seq_len = 32
micro_batch = 8
train_batches = make_batches(train_ids, seq_len, micro_batch, seed=42)
val_batches = make_batches(val_ids, seq_len, max(1, micro_batch // 2), seed=43)
print('Train batches:', len(train_batches), 'Val batches:', len(val_batches))

# Load BASE checkpoint
config = HerculeLMConfig.from_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)

base_checkpoint = 'training/checkpoints/n10/run-1790433607/step_00002951'
ckpt.load_checkpoint(base_checkpoint, model, strict=True)
print('Loaded BASE checkpoint (step 2951)')

# Training setup
lr = 0.0003  # Experiment A - Control
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
os.makedirs('training/checkpoints/n10_3_A_control_v2', exist_ok=True)
ckpt_root = Path('training/checkpoints/n10_3_A_control_v2')

# Training state
start_step = model._step_count  # Should be 2951
print('Starting from step:', start_step)

tokens_seen = 0
micro_index = 0
accum_grads = None
accum_loss, accum_count = 0.0, 0

eval_every = 500  # Evaluate every 500 steps for quick feedback
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
    "run_id": "n10_3_A_control_v2",
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

# Initial evaluation
val_loss = evaluate(model, val_batches)
print(f'Initial validation loss: {val_loss:.4f}')

# Training loop
print('Starting training...')
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
            print(f'step={step+1}/{total_target_steps} loss={mean_loss:.4f} lr={lr_current:.2e} gnorm={gnorm:.2f} {dt*1000:.0f}ms {eff_tokens/max(dt,1e-6):.0f}tok/s')
        
        # Evaluate
        if (step + 1) % eval_every == 0:
            val_loss = evaluate(model, val_batches)
            print(f'  valid loss={val_loss:.4f}')
        
        # Checkpoint
        if (step + 1) % ckpt_every == 0:
            save_checkpoint(step + 1)
            
except KeyboardInterrupt:
    print('Interrupted')
    save_checkpoint(step + 1)

save_checkpoint(step + 1)
print('Training complete')