import numpy as np
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM, KVCache

config = HerculeLMConfig.from_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)

# Test KV cache creation
kv = KVCache(
    num_layers=config.num_layers,
    batch_size=1,
    max_seq_len=config.context_length,
    hidden_size=config.hidden_size,
    num_heads=config.num_heads,
    head_dim=config.hidden_size // config.num_heads,
)
print('KV Cache created successfully')
print('Layers:', len(kv.layers))
print('K shape:', kv.layers[0]['k'].shape)
print('V shape:', kv.layers[0]['v'].shape)

# Test forward with KV cache
ids = np.array([[1, 2, 3, 4]], dtype=np.int64)
logits, _ = model.forward(ids, kv_cache=kv, start_pos=0)
print('Forward pass with KV cache: logits shape', logits.shape)
print('KV cache seq_len:', kv.seq_len)

# Test generate with KV cache
print('Testing generate with KV cache...')
out = model.generate([1, 2, 3], max_new_tokens=5, temperature=0.0, seed=0, use_kv_cache=True)
print('Generated:', out)

# Test generate without KV cache
print('Testing generate without KV cache...')
out2 = model.generate([1, 2, 3], max_new_tokens=5, temperature=0.0, seed=0, use_kv_cache=False)
print('Generated:', out2)
print('Match:', out == out2)