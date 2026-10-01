import json
import time
import numpy as np
import sys, os
sys.path.insert(0, '.')

os.environ['PYTHONUNBUFFERED'] = '1'

from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.data import make_batches

print('Loading tokenizer...', flush=True)
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
print(f'Tokenizer: {tokenizer.vocab_size} vocab, {len(tokenizer.merges)} merges', flush=True)

print('Loading corpus...', flush=True)
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

config = HerculeLMConfig.from_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)

base_checkpoint = 'training/checkpoints/n10/run-1790433607/step_00002951'
print('Loading BASE checkpoint...', flush=True)
ckpt.load_checkpoint(base_checkpoint, model, strict=True)
print(f'Loaded BASE checkpoint (step {model._step_count})', flush=True)

# Quick test: generate
start_ids = tokenizer.encode('Q: 2+2=\nA:')
out = model.generate(start_ids, max_new_tokens=10, temperature=0.0, seed=0)
print('Test generation:', tokenizer.decode(out), flush=True)

print('Quick training test (10 steps)...', flush=True)
lr = 0.0003
accum_steps = 1
grad_clip = 1.0
micro_index = 0
accum_grads = None
accum_loss, accum_count = 0.0, 0

def cosine_lr(step, total, base, warmup=50):
    if step < warmup:
        return base * max(0.05, (step + 1) / max(1, warmup))
    progress = min(1.0, (step - warmup) / max(1, total - warmup))
    return base * 0.5 * (1.0 + np.cos(np.pi * progress))

total_steps = 10
for step in range(total_steps):
    lr_current = cosine_lr(step, total_steps, lr)
    xs, ys = train_batches[micro_index % len(train_batches)]
    micro_index += 1
    logits, cache = model.forward(xs)
    loss, grads = model.loss_and_backward(logits, cache, ys)
    if accum_grads is None:
        accum_grads = {k: v.copy() for k, v in grads.items()}
    else:
        for key in accum_grads:
            accum_grads[key] += grads[key]
    accum_loss += float(loss)
    accum_count += 1
    mean_loss = accum_loss / max(1, accum_count)
    for key in accum_grads:
        accum_grads[key] /= max(1, accum_count)
    gnorm = model.clip_grads(accum_grads, grad_clip)
    model.adamw_step(accum_grads, lr_current)
    accum_grads, accum_loss, accum_count = None, 0.0, 0
    if step % 2 == 0:
        print(f'  step {step}: loss={mean_loss:.4f} gnorm={gnorm:.2f}', flush=True)

print('Quick test complete!', flush=True)