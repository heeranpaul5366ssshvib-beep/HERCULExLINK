import json
import sys
sys.path.insert(0, '.')

from models.hercule_lm.data import load_documents, split_documents, DataSource
from models.hercule_lm.tokenizer import HerculeBPETokenizer, CORE_SPECIALS

# Load original sources
sources_raw = json.loads(open('training/data/sources.json').read())
sources = [DataSource(**s) for s in sources_raw]
docs = load_documents('training/data/raw', sources, paragraphs=True)

# Split with seed 42
splits = split_documents(docs)
print('Train docs:', len(splits['train']))

# Train tokenizer with ONLY CORE_SPECIALS (matching BASE checkpoint)
train_texts = [d.text for d in splits['train']]
print('Training tokenizer on', len(train_texts), 'documents with CORE_SPECIALS only...')

tokenizer = HerculeBPETokenizer.train(
    train_texts, vocab_size=512, corpus_version="hercule-seed-v1", specials=CORE_SPECIALS
)

print('Tokenizer vocab_size:', tokenizer.vocab_size)
print('Tokenizer merges:', len(tokenizer.merges))
print('Tokenizer checksum:', tokenizer.checksum())
print('Expected BASE checksum: 1f9e34611ed16072')
print('Match:', tokenizer.checksum() == '1f9e34611ed16072')

# Check specials
for s in ['<PAD>', '<BOS>', '<EOS>', '<UNK>', '<OBSERVE>', '</OBSERVE>']:
    print(f'  {s}: {tokenizer.special_id(s)}')