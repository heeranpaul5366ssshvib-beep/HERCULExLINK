from models.hercule_lm.eval_harness import run_suite, model_predict_factory
from models.hercule_lm.config import get_preset
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt
import json

config = get_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)
ckpt.load_checkpoint('training/checkpoints/n10/run-1790519157/step_00005557', model, strict=True)
tokenizer = __import__('models.hercule_lm.tokenizer', fromlist=['HerculeBPETokenizer']).HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
predict = model_predict_factory(model, tokenizer, max_new_tokens=32, temperature=0.0, seed=42)

for suite in ['TOOL_USE', 'VERIFICATION', 'REASONING', 'HELD_OUT_ARITHMETIC']:
    result = run_suite(suite, predict, model_id='HERCULE-NANO', checkpoint='step_00005557')
    print(suite + ': mean=' + str(result['mean']) + ', passed=' + str(result['passed']) + '/' + str(result['n']))