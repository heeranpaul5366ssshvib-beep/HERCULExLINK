import time
import json
import psutil
import os

process = psutil.Process(os.getpid())

from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.optimized_model import OptimizedHerculeLM, benchmark_generation

print('=== CHECKPOINT 17: Real Model Benchmark ===')

config = HerculeLMConfig.from_preset('HERCULE-MICRO')
model = OptimizedHerculeLM(config, enable_kv_cache=True, enable_prompt_cache=True)
model.load('training/checkpoints/micro1/step_00003450', 'training/tokenizer/hercule-bpe-micro-v1')

categories = {
    'arithmetic': ['2 + 2 =', '10 * 5 =', '100 - 37 ='],
    'facts': ['The capital of France is', 'Water boils at', 'The largest planet is'],
    'coding': ['def hello():', 'def add(a, b):', 'class MyClass:'],
    'reasoning': ['If all A are B and all B are C, then', 'Because it rained, the ground is', 'Step 1: observe. Step 2:'],
    'chat': ['Hello!', 'How are you?', 'Good morning'],
}

results = {}
for cat, prompts in categories.items():
    print('\nBenchmarking ' + cat + '...')
    cat_results = benchmark_generation(model, prompts, max_new_tokens=16, temperature=0.0, runs=2)
    results[cat] = cat_results
    print('  Avg tokens/sec: {:.2f}'.format(cat_results["avg_tokens_per_sec"]))
    print('  Avg time: {:.1f}ms'.format(cat_results["avg_time_ms"]))
    for r in cat_results['per_run']:
        print('    Run {}: {:.2f} tok/s, {} tokens'.format(r["run"], r["tokens_per_sec"], r["total_tokens"]))

all_tps = [r['avg_tokens_per_sec'] for r in results.values()]
print('\n=== SUMMARY ===')
for cat, res in results.items():
    print('{}: {:.2f} tok/s'.format(cat, res["avg_tokens_per_sec"]))
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
        f.write('- Avg tokens/sec: {:.2f}\n'.format(res["avg_tokens_per_sec"]))
        f.write('- Avg time: {:.1f}ms\n'.format(res["avg_time_ms"]))
        for r in res['per_run']:
            f.write('  - Run {}: {:.2f} tok/s\n'.format(r["run"], r["tokens_per_sec"]))
    f.write('\n## Overall: {:.2f} tok/s\n'.format(report['overall_mean_tok_s']))

print('\nBenchmark report saved to reports/PC_FRONTIER_REAL_MODEL_BENCHMARK.md')