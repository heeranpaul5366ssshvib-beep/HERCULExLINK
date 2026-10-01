import numpy as np
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM, KVCache

config = HerculeLMConfig.from_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)

ids = [1, 2, 3]
ctx = config.context_length

print("=== Non-KV forward (full sequence) ===")
full_ids = np.array([ids + [5]], dtype=np.int64)
logits_full, cache_full = model.forward(full_ids)
print("Last token logits:", logits_full[0, -1, :5])

print("\n=== KV forward step by step ===")
kv = KVCache(
    num_layers=config.num_layers,
    batch_size=1,
    max_seq_len=config.context_length,
    hidden_size=config.hidden_size,
    num_heads=config.num_heads,
    head_dim=config.hidden_size // config.num_heads,
)

# First forward: prompt
print("\n--- First forward (prompt: [1,2,3]) ---")
window = np.array([ids], dtype=np.int64)
logits1, cache1 = model.forward(window, kv_cache=kv, start_pos=0)
print("Logits shape:", logits1.shape)
print("Cache layer 0 K sum:", kv.layers[0]['k'].sum())
print("Cache layer 0 K[:,:,0:3,:] sum:", kv.layers[0]['k'][:,:,:3,:].sum())

# Second forward: new token 5
print("\n--- Second forward (new token: 5) ---")
new_token = np.array([[5]], dtype=np.int64)
logits2, cache2 = model.forward(new_token, kv_cache=kv, start_pos=3)
print("Logits shape:", logits2.shape)
print("Cache layer 0 K sum:", kv.layers[0]['k'].sum())
print("Cache layer 0 K[:,:,0:4,:] sum:", kv.layers[0]['k'][:,:,:4,:].sum())

# Compare last token logits
print("\n--- Comparison ---")
print("Non-KV last token:", logits_full[0, -1, :5])
print("KV last token:", logits2[0, -1, :5])
print("Match:", np.allclose(logits_full[0, -1], logits2[0, -1]))

# Check attention scores in layer 0
print("\n--- Attention check ---")
# Non-KV attention probs
att_full = cache_full['L0.att'][3]  # probs
print("Non-KV att probs shape:", att_full.shape)
print("Non-KV att probs[0,0,-1,:]:", att_full[0,0,-1,:])

# KV attention probs  
att_kv = cache2['L0.att'][3]
print("KV att probs shape:", att_kv.shape)
print("KV att probs[0,0,-1,:]:", att_kv[0,0,-1,:])

# Check Q,K,V
print("\n--- Q,K,V check ---")
# Non-KV
q_full, k_full, v_full, _ = cache_full['L0.att'][:3]
print("Non-KV q shape:", q_full.shape)
print("Non-KV k shape:", k_full.shape)

# KV
q_kv, k_kv, v_kv, _ = cache2['L0.att'][:3]
print("KV q shape:", q_kv.shape)
print("KV k shape:", k_kv.shape)
print("KV k[:,:,:4,:] sum:", k_kv[:,:,:4,:].sum())
print("Cached k sum:", kv.layers[0]['k'][:,:,:3,:].sum())