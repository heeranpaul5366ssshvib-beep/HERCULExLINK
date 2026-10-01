import json
import sys
sys.path.insert(0, '.')

from models.hercule_lm.data import load_documents, split_documents, DataSource
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm.config import HerculeLMConfig

# Load original sources
sources_raw = json.loads(open('training/data/sources.json').read())
sources = [DataSource(**s) for s in sources_raw]
docs = load_documents('training/data/raw', sources, paragraphs=True)

# Split with seed 42 (same as BASE checkpoint)
splits = split_documents(docs)
print('Train docs:', len(splits['train']))
print('Val docs:', len(splits['validation']))
print('Test docs:', len(splits['test']))

# Train tokenizer on train split
train_texts = [d.text for d in splits['train']]
print('Training tokenizer on', len(train_texts), 'documents...')

tokenizer = HerculeBPETokenizer.train(
    train_texts, vocab_size=512, corpus_version="hercule-seed-v1"
)

print('Tokenizer vocab_size:', tokenizer.vocab_size)
print('Tokenizer merges:', len(tokenizer.merges))
print('Tokenizer checksum:', tokenizer.checksum())

# Save to a separate directory for BASE tokenizer
import os
os.makedirs('training/tokenizer/hercule-bpe-nano-v1-base', exist_ok=True)
tokenizer.save('training/tokenizer/hercule-bpe-nano-v1-base')
print('Saved BASE tokenizer to training/tokenizer/hercule-bpe-nano-v1-base')

# Verify
tok2 = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1-base')
print('Reloaded checksum:', tok2.checksum())
print('Match:', tok2.checksum() == tokenizer.checksum())