import json
import sys
sys.path.insert(0, '.')
from models.hercule_lm import eval_harness as eh
from models.hercule_lm import checkpoint as ckpt
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer

checkpoint = 'training/checkpoints/n10/run-1790433607/step_00002951'
manifest = json.loads(open(checkpoint + '/manifest.json').read())
config = HerculeLMConfig.from_dict(manifest['architecture'])
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
model = HerculeLM(config, seed=0)
ckpt.load_checkpoint(checkpoint, model, strict=True)

predict = eh.model_predict_factory(model, tokenizer, max_new_tokens=32, temperature=0.0, seed=0)

for suite in ['MATH', 'HELD_OUT_ARITHMETIC', 'ARC_STYLE', 'STRUCTURED_OUTPUT']:
    result = eh.run_suite(suite, predict, model_id='n10-base-2951', checkpoint='step_00002951')
    print(suite + ': mean={:.3f}, passed={}/{}, invalid={}'.format(result["mean"], result["passed"], result["n"], result["invalid"]))
    for r in result['results']:
        print('  {}: pass={} score={:.2f} out={}'.format(r["task"], r["pass"], r["score"], r["output"][:80]))