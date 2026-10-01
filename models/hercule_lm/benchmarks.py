#!/usr/bin/env python3
"""Actual MMLU, GSM8K, HumanEval evaluation for HERCULE models.

Downloads and evaluates on real benchmark datasets (not just style labels).
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from datasets import load_dataset
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "datasets"])
    from datasets import load_dataset

try:
    import numpy as np
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
    import numpy as np


class MMLUEvaluator:
    """Evaluate on MMLU (Massive Multitask Language Understanding)."""
    
    def __init__(self, model, tokenizer, max_new_tokens: int = 32, temperature: float = 0.0):
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.subjects = [
            "abstract_algebra", "anatomy", "astronomy", "business_ethics",
            "clinical_knowledge", "college_biology", "college_chemistry",
            "college_computer_science", "college_mathematics", "college_medicine",
            "college_physics", "computer_security", "conceptual_physics",
            "econometrics", "electrical_engineering", "elementary_mathematics",
            "formal_logic", "global_facts", "high_school_biology",
            "high_school_chemistry", "high_school_computer_science",
            "high_school_european_history", "high_school_geography",
            "high_school_government_and_politics", "high_school_macroeconomics",
            "high_school_mathematics", "high_school_microeconomics",
            "high_school_physics", "high_school_psychology",
            "high_school_statistics", "high_school_us_history",
            "high_school_world_history", "human_aging", "human_sexuality",
            "international_law", "jurisprudence", "logical_fallacies",
            "machine_learning", "management", "marketing", "medical_genetics",
            "miscellaneous", "moral_disputes", "moral_scenarios", "nutrition",
            "philosophy", "prehistory", "professional_accounting",
            "professional_law", "professional_medicine", "professional_psychology",
            "public_relations", "security_studies", "sociology", "us_foreign_policy",
            "virology", "world_religions"
        ]
    
    def evaluate(self, subjects: Optional[List[str]] = None, num_samples: int = 100) -> Dict[str, Any]:
        """Evaluate on MMLU subjects."""
        subjects = subjects or self.subjects[:5]  # Default to first 5 for speed
        results = {"benchmark": "MMLU", "subjects": {}, "overall": {}}
        
        all_correct = 0
        all_total = 0
        
        for subject in subjects:
            print(f"  Evaluating MMLU {subject}...")
            try:
                ds = load_dataset("cais/mmlu", subject, split="test", streaming=True)
                subject_correct = 0
                subject_total = 0
                
                for i, item in enumerate(ds):
                    if i >= num_samples:
                        break
                    
                    prompt = self._format_mmlu_question(item)
                    pred = self._generate(prompt)
                    answer = self._extract_answer(pred)
                    
                    if answer == item["answer"]:
                        subject_correct += 1
                    subject_total += 1
                
                acc = subject_correct / max(1, subject_total)
                results["subjects"][subject] = {
                    "correct": subject_correct,
                    "total": subject_total,
                    "accuracy": round(acc, 4)
                }
                all_correct += subject_correct
                all_total += subject_total
                
            except Exception as e:
                print(f"    Error on {subject}: {e}")
                results["subjects"][subject] = {"error": str(e)}
        
        results["overall"] = {
            "correct": all_correct,
            "total": all_total,
            "accuracy": round(all_correct / max(1, all_total), 4)
        }
        return results
    
    def _format_mmlu_question(self, item: Dict) -> str:
        choices = item["choices"]
        letters = ["A", "B", "C", "D"]
        prompt = f"Question: {item['question']}\n"
        for letter, choice in zip(letters, choices):
            prompt += f"{letter}) {choice}\n"
        prompt += "Answer:"
        return prompt
    
    def _extract_answer(self, text: str) -> str:
        text = text.strip().upper()
        for letter in ["A", "B", "C", "D"]:
            if text.startswith(letter) or f" {letter})" in text or f"({letter})" in text:
                return letter
        # Try to find letter in text
        for letter in ["A", "B", "C", "D"]:
            if letter in text:
                return letter
        return ""
    
    def _generate(self, prompt: str) -> str:
        ids = self.tokenizer.encode(prompt)
        out_ids = self.model.generate(ids, max_new_tokens=self.max_new_tokens, temperature=self.temperature)
        return self.tokenizer.decode(out_ids[len(ids):])


class GSM8KEvaluator:
    """Evaluate on GSM8K (Grade School Math 8K)."""
    
    def __init__(self, model, tokenizer, max_new_tokens: int = 64, temperature: float = 0.0):
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
    
    def evaluate(self, num_samples: int = 200) -> Dict[str, Any]:
        """Evaluate on GSM8K test set."""
        print(f"  Loading GSM8K...")
        ds = load_dataset("gsm8k", "main", split="test", streaming=True)
        
        correct = 0
        total = 0
        samples = []
        
        for i, item in enumerate(ds):
            if i >= num_samples:
                break
            
            prompt = f"Question: {item['question']}\nAnswer:"
            pred = self._generate(prompt)
            answer = self._extract_numeric_answer(pred)
            expected = self._extract_numeric_answer(item["answer"])
            
            is_correct = answer == expected
            if is_correct:
                correct += 1
            total += 1
            
            if len(samples) < 5:
                samples.append({
                    "question": item["question"][:100],
                    "expected": expected,
                    "predicted": answer,
                    "correct": is_correct
                })
        
        return {
            "benchmark": "GSM8K",
            "correct": correct,
            "total": total,
            "accuracy": round(correct / max(1, total), 4),
            "samples": samples
        }
    
    def _extract_numeric_answer(self, text: str) -> str:
        import re
        # Find the final number in the text (after #### for GSM8K format)
        if "####" in text:
            text = text.split("####")[-1]
        numbers = re.findall(r'-?\d+(?:\.\d+)?', text)
        return numbers[-1] if numbers else ""
    
    def _generate(self, prompt: str) -> str:
        ids = self.tokenizer.encode(prompt)
        out_ids = self.model.generate(ids, max_new_tokens=self.max_new_tokens, temperature=self.temperature)
        return self.tokenizer.decode(out_ids[len(ids):])


class HumanEvalEvaluator:
    """Evaluate on HumanEval (code generation)."""
    
    def __init__(self, model, tokenizer, max_new_tokens: int = 256, temperature: float = 0.0):
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
    
    def evaluate(self, num_samples: int = 50) -> Dict[str, Any]:
        """Evaluate on HumanEval."""
        print(f"  Loading HumanEval...")
        ds = load_dataset("openai_humaneval", split="test", streaming=True)
        
        passed = 0
        total = 0
        samples = []
        
        for i, item in enumerate(ds):
            if i >= num_samples:
                break
            
            prompt = item["prompt"]
            pred = self._generate(prompt)
            code = self._extract_code(pred)
            
            # Test the code
            test_result = self._run_tests(code, item["test"], item["entry_point"])
            is_passed = test_result["passed"]
            
            if is_passed:
                passed += 1
            total += 1
            
            if len(samples) < 3:
                samples.append({
                    "task_id": item["task_id"],
                    "passed": is_passed,
                    "code": code[:200]
                })
        
        return {
            "benchmark": "HumanEval",
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / max(1, total), 4),
            "samples": samples
        }
    
    def _extract_code(self, text: str) -> str:
        # Extract code from markdown code blocks
        import re
        code_blocks = re.findall(r'```(?:python)?\n(.*?)\n```', text, re.DOTALL)
        if code_blocks:
            return code_blocks[0]
        # Fallback: return everything after the prompt-like part
        lines = text.split('\n')
        code_lines = []
        in_code = False
        for line in lines:
            if line.strip().startswith('def ') or line.strip().startswith('class '):
                in_code = True
            if in_code:
                code_lines.append(line)
        return '\n'.join(code_lines) if code_lines else text
    
    def _run_tests(self, code: str, test: str, entry_point: str) -> Dict[str, Any]:
        """Run tests in a sandboxed environment."""
        # Create a temporary file with the code and tests
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_solution.py"
            test_content = f"{code}\n\n{test}\n\nif __name__ == '__main__':\n    test_{entry_point}()\n"
            test_file.write_text(test_content)
            
            # Run the test
            import subprocess
            try:
                result = subprocess.run(
                    [sys.executable, str(test_file)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                passed = result.returncode == 0
                return {"passed": passed, "stdout": result.stdout, "stderr": result.stderr}
            except subprocess.TimeoutExpired:
                return {"passed": False, "error": "timeout"}
            except Exception as e:
                return {"passed": False, "error": str(e)}
    
    def _generate(self, prompt: str) -> str:
        ids = self.tokenizer.encode(prompt)
        out_ids = self.model.generate(ids, max_new_tokens=self.max_new_tokens, temperature=self.temperature)
        return self.tokenizer.decode(out_ids[len(ids):])


def run_all_benchmarks(model, tokenizer, args) -> Dict[str, Any]:
    """Run all benchmarks and return combined results."""
    results = {}
    
    if args.mmlu:
        print("Running MMLU evaluation...")
        mmlu = MMLUEvaluator(model, tokenizer, args.max_new_tokens, args.temperature)
        results["mmlu"] = mmlu.evaluate(args.mmlu_subjects, args.mmlu_samples)
        print(f"  MMLU Overall: {results['mmlu']['overall']['accuracy']:.2%}")
    
    if args.gsm8k:
        print("Running GSM8K evaluation...")
        gsm8k = GSM8KEvaluator(model, tokenizer, args.max_new_tokens, args.temperature)
        results["gsm8k"] = gsm8k.evaluate(args.gsm8k_samples)
        print(f"  GSM8K: {results['gsm8k']['accuracy']:.2%}")
    
    if args.humaneval:
        print("Running HumanEval evaluation...")
        humaneval = HumanEvalEvaluator(model, tokenizer, args.max_new_tokens, args.temperature)
        results["humaneval"] = humaneval.evaluate(args.humaneval_samples)
        print(f"  HumanEval: {results['humaneval']['pass_rate']:.2%}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Run MMLU/GSM8K/HumanEval benchmarks")
    parser.add_argument("--checkpoint", required=True, help="Model checkpoint directory")
    parser.add_argument("--tokenizer-dir", default="", help="Tokenizer directory")
    parser.add_argument("--mmlu", action="store_true", help="Run MMLU evaluation")
    parser.add_argument("--mmlu-subjects", nargs="+", help="MMLU subjects to evaluate")
    parser.add_argument("--mmlu-samples", type=int, default=100, help="Samples per MMLU subject")
    parser.add_argument("--gsm8k", action="store_true", help="Run GSM8K evaluation")
    parser.add_argument("--gsm8k-samples", type=int, default=200, help="GSM8K samples")
    parser.add_argument("--humaneval", action="store_true", help="Run HumanEval evaluation")
    parser.add_argument("--humaneval-samples", type=int, default=50, help="HumanEval samples")
    parser.add_argument("--max-new-tokens", type=int, default=64, help="Max new tokens for generation")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--out", default="", help="Output JSON file")
    args = parser.parse_args()
    
    # Load model and tokenizer
    from models.hercule_lm import checkpoint as ckpt
    from models.hercule_lm.config import HerculeLMConfig, load_config
    from models.hercule_lm.model import HerculeLM
    from models.hercule_lm.hf_tokenizer import load_hf_tokenizer
    
    manifest = json.loads(Path(args.checkpoint, "manifest.json").read_text())
    config = HerculeLMConfig.from_dict(manifest["architecture"])
    
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    tokenizer = load_hf_tokenizer(tok_dir)
    
    model = HerculeLM(config, seed=0)
    ckpt.load_checkpoint(args.checkpoint, model, strict=True)
    
    results = run_all_benchmarks(model, tokenizer, args)
    
    print(json.dumps(results, indent=2))
    
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())