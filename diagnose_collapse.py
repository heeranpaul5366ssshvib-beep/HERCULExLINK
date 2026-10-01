"""Quick collapse diagnosis - minimal output."""

from collections import Counter
import math
from models.hercule_lm.config import get_preset
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt


def main():
    config = get_preset('HERCULE-NANO')
    model = HerculeLM(config, seed=42)
    ckpt.load_checkpoint('training/checkpoints/n10/run-1790433607/step_00002951', model, strict=True)
    tokenizer = __import__('models.hercule_lm.tokenizer', fromlist=['HerculeBPETokenizer']).HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')

    def generate(prompt, max_new_tokens=64):
        input_ids = tokenizer.encode(prompt)
        output_ids = model.generate(input_ids, max_new_tokens=max_new_tokens, temperature=0.0, seed=42)
        return tokenizer.decode(output_ids)

    test_prompts = [
        "Q: Calculate 2 + 2.\nA:",
        "Q: Calculate 10 + 20.\nA:",
        "Call calculator mul with a=5, b=3\nA:",
    ]

    all_tokens = []
    for prompt in test_prompts:
        output = generate(prompt, max_new_tokens=64)
        continuation = output[len(prompt):]
        tokens = tokenizer.encode(continuation)
        print(f"Prompt: {prompt[:50]}...")
        print(f"  Tokens: {tokens[:20]}")
        print()
        all_tokens.extend(tokens)

    freq = Counter(all_tokens)
    print("Top 10 tokens in generated output:")
    for token_id, count in freq.most_common(10):
        token_str = tokenizer.decode([token_id]) if token_id in tokenizer._inv else f"UNK({token_id})"
        print(f"  {token_id} ({repr(token_str)}): {count}")

    total = len(all_tokens)
    if total > 0:
        entropy = -sum((count/total) * math.log2(count/total) for count in freq.values())
        print(f"\nToken entropy: {entropy:.3f} bits")
        print(f"Total tokens: {total}")
        print(f"Unique tokens: {len(freq)}")

    special_tokens = {
        tokenizer.bos_id: "<BOS>",
        tokenizer.eos_id: "<EOS>",
        tokenizer.pad_id: "<PAD>",
        tokenizer.unk_id: "<UNK>",
    }
    print("\nSpecial token frequencies:")
    for tid, name in special_tokens.items():
        if tid in freq:
            print(f"  {name} (id={tid}): {freq[tid]}")

    lt_id = None
    for tid, name in [(k, v) for k, v in tokenizer.vocab.items() if v == b'<']:
        lt_id = tid
        break
    if lt_id and lt_id in freq:
        print(f"\n'<' token (id={lt_id}) frequency: {freq[lt_id]} ({freq[lt_id]/total*100:.1f}%)")

    print("\n--- Target token distribution (first 1000 validation tokens) ---")
    from models.hercule_lm.data import load_documents, split_documents, encode_split, DataSource
    import json
    sources = [DataSource(**s) for s in json.loads(open('training/data/sources.json').read())]
    docs = load_documents('training/data/raw', sources, paragraphs=True)
    splits = split_documents(docs)
    valid_stream = encode_split(tokenizer, splits['validation'], 32, seed=42)
    valid_tokens = valid_stream[:1000]
    valid_freq = Counter(valid_tokens)
    print("Top 20 validation target tokens:")
    for tid, count in valid_freq.most_common(20):
        tok = tokenizer.decode([tid]) if tid in tokenizer._inv else f"UNK({tid})"
        print(f"  {tid} ({repr(tok)}): {count}")

if __name__ == "__main__":
    main()