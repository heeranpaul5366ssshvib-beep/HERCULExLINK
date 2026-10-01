from models.hercule_lm.eval_harness import run_all, model_predict_factory, build_suite, verify_task
from models.hercule_lm.config import get_preset
from models.hercule_lm.model import HerculeLM
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm import checkpoint as ckpt

# Load model
config = get_preset('HERCULE-NANO')
model = HerculeLM(config, seed=42)
ckpt.load_checkpoint('training/checkpoints/n10/run-1790433607/step_00002951', model, strict=True)

# Load tokenizer
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')

# Quick evaluation on just a few arithmetic tasks
predict = model_predict_factory(model, tokenizer, max_new_tokens=16, temperature=0.0, seed=42)

# Test arithmetic
tasks = build_suite('MATH')
print('MATH tasks:', len(tasks))
for task in tasks[:3]:
    out = predict(task)
    verdict = verify_task(task, out['text'])
    print('Task:', task['id'])
    print('  Prompt:', task['prompt'])
    print('  Expected:', task['reference'])
    print('  Got:', out['text'][:50])
    print('  Pass:', verdict['pass'], 'Score:', verdict['score'])
    print()

# Test tool use
tasks = build_suite('TOOL_USE')
print('TOOL_USE tasks:', len(tasks))
for task in tasks[:2]:
    out = predict(task)
    verdict = verify_task(task, out['text'])
    print('Task:', task['id'])
    print('  Prompt:', task['prompt'])
    print('  Got:', out['text'][:100])
    print('  Pass:', verdict['pass'], 'Score:', verdict['score'])
    print()

# Test verification
tasks = build_suite('VERIFICATION')
print('VERIFICATION tasks:', len(tasks))
for task in tasks[:2]:
    out = predict(task)
    verdict = verify_task(task, out['text'])
    print('Task:', task['id'])
    print('  Prompt:', task['prompt'])
    print('  Got:', out['text'][:100])
    print('  Pass:', verdict['pass'], 'Score:', verdict['score'])
    print()