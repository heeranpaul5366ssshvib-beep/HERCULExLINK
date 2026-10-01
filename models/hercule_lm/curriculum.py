from __future__ import annotations
"""Curriculum Learning Pipeline (N9 §4).

Orchestrates staged training across domains:
- Stage A: Language (syntax, vocab, facts, instructions)
- Stage B: Structured Reasoning (arithmetic, logic, sequences, transforms)
- Stage C: Code (Python, algorithms, debugging)
- Stage D: Cognitive OS Data (goals, plans, tools, verification, memory)
- Stage E: ARC Reasoning (objects, relations, transformations, programs)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Iterator, Tuple, Any

import numpy as np

from .data import Document, DataSource, load_documents, split_documents, encode_split, cached_stream, make_batches
from .synthetic_reasoning import (
    ReasoningExample, generate_curriculum, curriculum_stats,
    generate_arithmetic, generate_comparison, generate_sequence,
    generate_symbolic_transform, generate_code, generate_tool_use,
    generate_verification, generate_arc_grid
)
from .tokenizer import HerculeBPETokenizer
from .config import HerculeLMConfig


@dataclass
class CurriculumStage:
    """Configuration for a curriculum stage."""
    name: str
    domains: List[str]
    difficulty_range: Tuple[int, int]
    weight: float
    tokens_per_step: int
    steps: int
    description: str = ""


# Default curriculum schedule (N9 §4)
DEFAULT_CURRICULUM = [
    CurriculumStage(
        name="STAGE_A_LANGUAGE",
        domains=["language", "facts", "instructions"],
        difficulty_range=(1, 1),
        weight=0.4,
        tokens_per_step=10000,
        steps=500,
        description="Basic syntax, vocabulary, factual patterns, short instruction following"
    ),
    CurriculumStage(
        name="STAGE_B_STRUCTURED",
        domains=["arithmetic", "comparison", "sequence", "symbolic_transform"],
        difficulty_range=(1, 3),
        weight=0.25,
        tokens_per_step=15000,
        steps=1000,
        description="Arithmetic, comparisons, sequences, symbolic transformations"
    ),
    CurriculumStage(
        name="STAGE_C_CODE",
        domains=["code"],
        difficulty_range=(1, 3),
        weight=0.15,
        tokens_per_step=20000,
        steps=500,
        description="Python, algorithms, debugging, structured code generation"
    ),
    CurriculumStage(
        name="STAGE_D_COGNITIVE_OS",
        domains=["tool_use", "verification", "memory", "planning"],
        difficulty_range=(1, 3),
        weight=0.1,
        tokens_per_step=20000,
        steps=500,
        description="Goals, plans, observations, tool requests, verification, memory"
    ),
    CurriculumStage(
        name="STAGE_E_ARC",
        domains=["arc_grid"],
        difficulty_range=(1, 3),
        weight=0.1,
        tokens_per_step=25000,
        steps=500,
        description="Objects, relations, transformations, compositional programs"
    ),
]


class CurriculumManager:
    """Manages curriculum data generation and scheduling."""
    
    def __init__(
        self,
        config: HerculeLMConfig,
        tokenizer: HerculeBPETokenizer,
        curriculum: List[CurriculumStage] = None,
        seed: int = 42,
        cache_dir: str = "training/curriculum_cache",
        corpus_dir: str = "training/data/raw",
        sources_path: str = "training/data/sources.json"
    ):
        self.config = config
        self.tokenizer = tokenizer
        self.curriculum = curriculum or DEFAULT_CURRICULUM
        self.seed = seed
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.corpus_dir = corpus_dir
        self.sources_path = sources_path
        self._stage_data: Dict[str, np.ndarray] = {}
        self._stage_batches: Dict[str, List[Tuple[np.ndarray, np.ndarray]]] = {}
        self._synthetic_examples: List[ReasoningExample] = []
    
    def prepare_stage(self, stage: CurriculumStage) -> np.ndarray:
        """Generate or load token stream for a stage."""
        cache_key = f"{stage.name}_v{stage.weight}_d{stage.difficulty_range[0]}-{stage.difficulty_range[1]}"
        cache_path = self.cache_dir / f"{cache_key}.npy"
        manifest_path = self.cache_dir / f"{cache_key}.manifest.json"
        
        # Check cache
        if cache_path.exists() and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("config_hash") == self.config.architecture_hash():
                print(f"Loading cached stage: {stage.name}")
                return np.load(cache_path)
        
        print(f"Generating stage: {stage.name}")
        
        # Generate synthetic data for this stage
        synthetic_examples = self._generate_synthetic_for_stage(stage)
        
        # Load natural language data for STAGE_A
        natural_stream = np.array([], dtype=np.int64)
        if "language" in stage.domains or "facts" in stage.domains or "instructions" in stage.domains:
            sources = [DataSource(**s) for s in json.loads(Path(self.sources_path).read_text())]
            docs = load_documents(self.corpus_dir, sources, paragraphs=True)
            splits = split_documents(docs)
            natural_stream = encode_split(self.tokenizer, splits["train"], self.config.context_length // 2, seed=self.seed)
        
        # Convert synthetic examples to token stream
        synthetic_texts = [f"{ex.problem} {ex.target}" for ex in synthetic_examples]
        synthetic_stream = encode_split(self.tokenizer, 
            [Document(f"synth_{i}", "synthetic", "HERCULE-authored", t) for i, t in enumerate(synthetic_texts)],
            self.config.context_length // 2, seed=self.seed)
        
        # Combine streams according to weight
        if len(natural_stream) > 0 and len(synthetic_stream) > 0:
            # Mix: weight proportion synthetic
            total_target = int(len(natural_stream) / (1 - stage.weight)) if stage.weight < 1 else len(synthetic_stream)
            nat_take = min(len(natural_stream), int(total_target * (1 - stage.weight)))
            syn_take = min(len(synthetic_stream), int(total_target * stage.weight))
            
            # Shuffle and take
            rng = np.random.default_rng(self.seed)
            nat_idx = rng.permutation(len(natural_stream))[:nat_take]
            syn_idx = rng.permutation(len(synthetic_stream))[:syn_take]
            
            combined = np.concatenate([natural_stream[nat_idx], synthetic_stream[syn_idx]])
            rng.shuffle(combined)
        elif len(synthetic_stream) > 0:
            combined = synthetic_stream
        else:
            combined = natural_stream
        
        # Cache
        np.save(cache_path, combined)
        manifest = {
            "config_hash": self.config.architecture_hash(),
            "stage": stage.name,
            "tokens": int(combined.size),
            "domains": stage.domains,
            "weight": stage.weight,
        }
        manifest_path.write_text(json.dumps(manifest, indent=1))
        
        print(f"  Stage {stage.name}: {combined.size} tokens")
        return combined
    
    def _generate_synthetic_for_stage(self, stage: CurriculumStage) -> List[ReasoningExample]:
        """Generate synthetic examples for a curriculum stage."""
        all_examples = []
        d_min, d_max = stage.difficulty_range
        
        for domain in stage.domains:
            if domain == "arithmetic":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_arithmetic(self.seed + 1000*d, d))
            elif domain == "comparison":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_comparison(self.seed + 2000*d, d))
            elif domain == "sequence":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_sequence(self.seed + 3000*d, d))
            elif domain == "symbolic_transform":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_symbolic_transform(self.seed + 4000*d, d))
            elif domain == "code":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_code(self.seed + 5000*d, d))
            elif domain == "tool_use":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_tool_use(self.seed + 6000*d, d))
            elif domain == "verification":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_verification(self.seed + 7000*d, d))
            elif domain == "arc_grid":
                for d in range(d_min, d_max + 1):
                    all_examples.extend(generate_arc_grid(self.seed + 8000*d, d))
            elif domain in ("language", "facts", "instructions", "memory", "planning"):
                # These use natural language data; synthetic generation optional
                pass
        
        return all_examples
    
    def get_stage_batches(
        self, 
        stage: CurriculumStage, 
        batch_size: int, 
        micro_batch: int,
        seq_len: int
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Get batches for a stage."""
        cache_key = f"{stage.name}_bs{batch_size}_mb{micro_batch}_sl{seq_len}"
        
        if cache_key in self._stage_batches:
            return self._stage_batches[cache_key]
        
        stream = self.prepare_stage(stage)
        batches = make_batches(stream, seq_len, micro_batch, seed=self.seed)
        self._stage_batches[cache_key] = batches
        return batches
    
    def curriculum_iterator(
        self,
        batch_size: int,
        micro_batch: int,
        seq_len: int,
        stage_order: Optional[List[str]] = None
    ) -> Iterator[Tuple[str, Tuple[np.ndarray, np.ndarray]]]:
        """Iterate through curriculum stages, yielding (stage_name, (xs, ys)) batches."""
        stage_names = stage_order or [s.name for s in self.curriculum]
        
        for stage_name in stage_names:
            stage = next(s for s in self.curriculum if s.name == stage_name)
            batches = self.get_stage_batches(stage, batch_size, micro_batch, seq_len)
            print(f"Curriculum: {stage_name} - {len(batches)} batches")
            for batch in batches:
                yield stage_name, batch
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all stages."""
        stats = {}
        for stage in self.curriculum:
            stream = self.prepare_stage(stage)
            stats[stage.name] = {
                "tokens": int(stream.size),
                "domains": stage.domains,
                "difficulty_range": stage.difficulty_range,
                "weight": stage.weight,
                "planned_steps": stage.steps,
            }
        return stats


def create_curriculum_schedule(
    total_steps: int,
    curriculum: List[CurriculumStage] = None
) -> List[Tuple[str, int]]:
    """Create a step schedule from curriculum stages.
    
    Returns list of (stage_name, step_count) tuples.
    """
    curriculum = curriculum or DEFAULT_CURRICULUM
    total_weight = sum(s.weight * s.steps for s in curriculum)
    schedule = []
    
    for stage in curriculum:
        proportion = (stage.weight * stage.steps) / total_weight
        steps = max(1, int(total_steps * proportion))
        schedule.append((stage.name, steps))
    
    # Adjust to match total_steps exactly
    diff = total_steps - sum(s for _, s in schedule)
    if diff != 0:
        schedule[-1] = (schedule[-1][0], schedule[-1][1] + diff)
    
    return schedule


if __name__ == "__main__":
    from .config import get_preset
    
    config = get_preset("HERCULE-NANO")
    tokenizer = HerculeBPETokenizer.train([], vocab_size=512)  # dummy
    
    mgr = CurriculumManager(config, tokenizer, seed=42)
    stats = mgr.get_stats()
    print(json.dumps(stats, indent=1))
    
    schedule = create_curriculum_schedule(2500)
    print("\nSchedule:")
    for stage, steps in schedule:
        print(f"  {stage}: {steps} steps")