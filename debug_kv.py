import numpy as np
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM, KVCache

config = HerculeLMConfig.from_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)

# Test with a simple prompt and trace through
ids = [1, 2, 3]  # Simple prompt
ctx = config.context_length

print("=== First forward (full prompt) ===")
window = np.array([ids[-ctx:]], dtype=np.int64)
print("Input shape:", window.shape)

kv = KVCache(
    num_layers=config.num_layers,
    batch_size=1,
    max_seq_len=config.context_length,
    hidden_size=config.hidden_size,
    num_heads=config.num_heads,
    head_dim=config.hidden_size // config.num_heads,
)

logits, _ = model.forward(window, kv_cache=kv, start_pos=0)
print("Logits shape:", logits.shape)
print("KV cache layers:", len(kv.layers))
print("Layer 0 K shape:", kv.layers[0]['k'].shape)
print("Layer 0 K[:,:,0:4,:] (first 4 tokens):", kv.layers[0]['k'][:,:,:4,:].sum())

print("\n=== Second forward (new token) ===")
new_token = np.array([[5]], dtype=np.int64)
print("Input shape:", new_token.shape)
logits2, _ = model.forward(new_token, kv_cache=kv, start_pos=len(ids))
print("Logits2 shape:", logits2.shape)
print("KV cache K[:,:,0:5,:] sum:", kv.layers[0]['k'][:,:,:5,:].sum())

# Check cache get
cached_k, cached_v = kv.get(0, len(ids))
print("Cached K shape:", cached_k.shape)
print("Cached K sum:", cached_k.sum())

# Compare with non-KV forward
print("\n=== Non-KV forward for same input ===")
full_ids = np.array([ids + [5]], dtype=np.int64)
logits_full, _ = model.forward(full_ids)
print("Full logits shape:", logits_full.shape)
print("Last token logits (non-KV):", logits_full[0, -1, :5])
print("Last token logits (KV):", logits2[0, -1, :5])