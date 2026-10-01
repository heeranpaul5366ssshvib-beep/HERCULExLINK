import time
import json
import psutil
import os

process = psutil.Process(os.getpid())

from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.optimized_model import OptimizedHerculeLM

print('=== CHECKPOINT 17: Real Model Benchmark (Simple) ===')

config = HerculeLMConfig.from_preset('HERCULE-MICRO')
model = OptimizedHerculeLM(config, enable_kv_cache=True, enable_prompt_cache=True)
model.load('training/checkpoints/micro1/step_00003450', 'training/tokenizer/hercule-bpe-micro-v1')

categories = {
    'arithmetic': ['2 + 2 ='],
    'facts': ['The capital of France is'],
    'coding': ['def hello():'],
    'reasoning': ['If all A are B then'],
    'chat': ['Hello!'],
}

results = {}
for cat, prompts in categories.items():
    print('\nBenchmarking ' + cat + '...')
    model.reset_metrics()
    start = time.perf_counter()
    for p in prompts:
        model.generate(p, max_new_tokens=8, temperature=0.0)
    elapsed = (time.perf_counter() - start) * 1000
    metrics = model.get_metrics()
    tps = metrics.get('tokens_per_sec', 0)
    results[cat] = {'tokens_per_sec': tps, 'time_ms': elapsed}
    print('  tokens/sec: {:.2f}'.format(tps))
    print('  time: {:.1f}ms'.format(elapsed))

all_tps = [r['tokens_per_sec'] for r in results.values()]
print('\n=== SUMMARY ===')
for cat, res in results.items():
    print('{}: {:.2f} tok/s'.format(cat, res["tokens_per_sec"]))
print('Overall mean: {:.2f} tok/s'.format(sum(all_tps)/len(all_tps)))

report = {
    'model': 'hercule-lm-micro',
    'checkpoint': 'training/checkpoints/micro1/step_00003450',
    'parameter_count': config.parameter_count(),
    'context_length': config.context_length,
    'vocab_size': config.vocab_size,
    'categories': results,
    'overall_mean_tok_s': sum(all_tps)/len(all_tps),
    'load_time_ms': model.metrics['load_time_ms'],
}

os.makedirs('reports', exist_ok=True)
with open('reports/PC_FRONTIER_REAL_MODEL_BENCHMARK.md', 'w') as f:
    f.write('# PC-Frontier Real Model Benchmark\n\n')
    f.write('Model: ' + report['model'] + '\n')
    f.write('Parameters: ' + str(report['parameter_count']) + '\n')
    f.write('Context: ' + str(report['context_length']) + '\n')
    f.write('Vocab: ' + str(report['vocab_size']) + '\n')
    f.write('Load time: {:.1f}ms\n\n'.format(report['load_time_ms']))
    f.write('## Per-Category Results\n\n')
    for cat, res in results.items():
        f.write('### ' + cat + '\n')
        f.write('- Avg tokens/sec: {:.2f}\n'.format(res["tokens_per_sec"]))
        f.write('- Time: {:.1f}ms\n'.format(res["time_ms"]))
    f.write('\n## Overall: {:.2f} tok/s\n'.format(report['overall_mean_tok_s']))

print('\nBenchmark report saved to reports/PC_FRONTIER_REAL_MODEL_BENCHMARK.md')