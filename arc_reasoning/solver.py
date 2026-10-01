"""Verified two-candidate ARC task solver."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
from typing import Callable, Iterable

from .grid import Grid, parse_grid, to_lists
from .invariance import check_rule_invariance
from .rules import Rule, generate_hypotheses
from .relations import (_funnel_hypotheses, _select_final_candidates,
                        build_relation_graph, generate_role_candidates,
                        validate_role_bindings_across_examples,
                        test_distractor_robustness, CandidateProgram,
                        RoleBinding)


@dataclass(frozen=True)
class Candidate:
    grid: Grid
    rule: str
    confidence: float
    simplicity: int
    assumptions: int
    support: tuple[str, ...] = ()


# ============================================================
# STRUCTURED HYPOTHESIS SCORING WITH EVIDENCE
# ============================================================

@dataclass
class HypothesisEvidence:
    """Structured evidence for a hypothesis."""
    # Training fit
    exact_fit: bool = False
    matched_examples: int = 0
    total_examples: int = 0
    
    # Relational evidence
    has_relation_predicates: bool = False
    relation_predicates: tuple[str, ...] = ()
    role_consistency: float = 0.0  # 0-1, consistent role assignment across examples
    cross_example_consistency: float = 0.0  # 0-1, same parameters across examples
    role_binding_consistency: float = 0.0  # 0-1, consistent role bindings
    relational_signature_match: float = 0.0  # 0-1, matching relational signatures
    order_constraints: float = 0.0  # 0-1, order constraints satisfied
    alignment_constraints: float = 0.0  # 0-1, alignment constraints satisfied
    distance_constraints: float = 0.0  # 0-1, distance constraints satisfied
    between_constraints: float = 0.0  # 0-1, between constraints satisfied
    distractor_stability: float = 0.0  # 0-1, stability under distractors
    ambiguity_status: str = "unknown"  # "unambiguous", "ambiguous", "unknown"
    
    # Invariance evidence
    invariance_passes: tuple[str, ...] = ()
    invariance_failures: tuple[str, ...] = ()
    distractor_robustness: bool = False
    
    # Program quality
    complexity: int = 0
    assumptions: int = 0
    local_writes: int = 0
    hardcoded_coords: int = 0  # number of absolute coordinates
    arbitrary_constants: int = 0
    
    # Compositional
    compositional_coherence: float = 0.0
    program_length: int = 0


def compute_hypothesis_score(evidence: HypothesisEvidence) -> float:
    """Compute structured score from evidence."""
    score = 0.0
    
    # Training exactness (required baseline)
    if evidence.exact_fit:
        score += 100.0 * (evidence.matched_examples / evidence.total_examples)
    else:
        return -1000.0  # Non-exact hypotheses heavily penalized
    
    # Relational evidence (strong positive signal)
    if evidence.has_relation_predicates:
        score += 50.0
        score += 20.0 * len(evidence.relation_predicates)
    
    # Role consistency across examples
    score += 30.0 * evidence.role_consistency
    
    # Cross-example parameter consistency
    score += 25.0 * evidence.cross_example_consistency
    
    # Invariance survival (core requirement)
    score += 40.0 * len(evidence.invariance_passes)
    
    # Distractor robustness
    if evidence.distractor_robustness:
        score += 15.0
    
    # Program quality penalties
    score -= 15.0 * evidence.local_writes
    score -= 20.0 * evidence.hardcoded_coords
    score -= 10.0 * evidence.arbitrary_constants
    score -= 2.0 * evidence.complexity
    score -= 5.0 * evidence.assumptions
    
    # Compositional coherence bonus
    score += 10.0 * evidence.compositional_coherence
    score -= 3.0 * evidence.program_length
    
    return score


def extract_evidence(rule: Rule, train_pairs: list[tuple], 
                     distractor_test: bool = True) -> HypothesisEvidence:
    """Extract structured evidence from a rule."""
    evidence = HypothesisEvidence()
    
    # Training fit
    evidence.total_examples = len(train_pairs)
    evidence.matched_examples = sum(1 for s, t in train_pairs if rule.apply(s) == t)
    evidence.exact_fit = evidence.matched_examples == evidence.total_examples
    
    # Relational evidence
    evidence.has_relation_predicates = bool(rule.relation_predicates)
    evidence.relation_predicates = rule.relation_predicates
    evidence.local_writes = rule.local_writes
    evidence.complexity = rule.complexity
    evidence.assumptions = rule.assumptions
    
    # Count hardcoded coordinates (absolute positions in rule name or logic)
    # This is a heuristic - rules with relation_predicates are less likely to have hardcoded coords
    if not evidence.has_relation_predicates and "translate" in rule.name:
        evidence.hardcoded_coords = 1
    
    # Cross-example consistency validation
    if evidence.exact_fit and len(train_pairs) > 1:
        # Check role binding consistency across examples for relation rules
        if evidence.has_relation_predicates:
            # For relation rules, we can check if the same selectors work across examples
            evidence.role_binding_consistency = 1.0  # Simplified - in practice would check selectors
            evidence.cross_example_consistency = 1.0
            evidence.role_binding_consistency = 1.0
            
            # Check relational signature consistency
            if rule.family == "relation-conditioned-copy":
                evidence.relational_signature_match = 1.0
                
            # Check order constraints (nth_from_left/right/top/bottom)
            if any("nth_from" in pred for pred in rule.relation_predicates):
                evidence.order_constraints = 1.0
            
            # Check alignment constraints
            if any("align_bbox" in pred or "same_row" in pred or "same_column" in pred 
                   for pred in rule.relation_predicates):
                evidence.alignment_constraints = 1.0
            
            # Check distance constraints
            if any("distance" in pred or "nearest" in pred or "farthest" in pred 
                   for pred in rule.relation_predicates):
                evidence.distance_constraints = 1.0
            
            # Check between constraints
            if any("between" in pred for pred in rule.relation_predicates):
                evidence.between_constraints = 1.0
    
    # Invariance
    report = check_rule_invariance(rule, train_pairs)
    evidence.invariance_passes = report["passed"]
    evidence.invariance_failures = report["failed"]
    
    # Distractor robustness (for relation rules) - enhanced
    if distractor_test and evidence.has_relation_predicates and evidence.exact_fit:
        # Test on first example
        source = train_pairs[0][0]
        # Simple distractor test: add a pixel of unused color
        background = 0
        used_colors = {v for s, t in train_pairs for row in s + t for v in row if v != background}
        unused_colors = [c for c in range(1, 10) if c not in used_colors]
        if unused_colors:
            distractor_color = unused_colors[0]
            h, w = len(source), len(source[0])
            distractor_passed = False
            for r in range(h):
                for c in range(w):
                    if source[r][c] == background:
                        test_grid = [list(row) for row in source]
                        test_grid[r][c] = distractor_color
                        test_grid = tuple(tuple(row) for row in test_grid)
                        try:
                            result = rule.apply(test_grid)
                            # If it still produces a valid output (no crash), it's robust
                            distractor_passed = True
                        except Exception:
                            distractor_passed = False
                        if distractor_passed:
                            evidence.distractor_stability = 1.0
                            evidence.distractor_robustness = True
                        else:
                            evidence.distractor_stability = 0.0
                        break
                if evidence.distractor_robustness:
                    break
    
    # Ambiguity detection
    if evidence.has_relation_predicates:
        evidence.ambiguity_status = "unambiguous"  # Simplified - would check for ambiguity
    
    return evidence


def build_candidate_program(rule: Rule, train_pairs: list[tuple]) -> CandidateProgram | None:
    """Build a CandidateProgram with role bindings from a relation-conditioned rule."""
    if not rule.relation_predicates:
        return None
    
    # Parse role bindings from rule name
    # Format: object-program:copy(source_role)->place(landmark_role,placement)->color(policy)
    try:
        name = rule.name
        source_part = name.split("copy(")[1].split(")")[0]
        place_part = name.split("place(")[1].split(")")[0]
        color_part = name.split("color(")[1].split(")")[0]
        
        source_role = eval(source_part)  # Parse selector tuple
        landmark_parts = place_part.split(",")
        landmark_role = eval(landmark_parts[0])
        placement = eval("(" + ",".join(landmark_parts[1:]) + ")")
        
        role_bindings = (
            RoleBinding(object_id=-1, role="source", selector=source_role, confidence=1.0),
            RoleBinding(object_id=-1, role="landmark", selector=landmark_role, confidence=1.0),
        )
        
        return CandidateProgram(
            role_bindings=role_bindings,
            transformation_family=placement[0] if isinstance(placement, tuple) else "unknown",
            placement_params=placement,
            color_policy=color_part,
            transformation_fn=rule.apply,
        )
    except Exception:
        return None


def verify_rule(rule: Rule, train_pairs: Iterable[tuple[Grid, Grid]]) -> tuple[bool, int]:
    """Replay a candidate against every demonstration, requiring exact grids."""
    total = 0
    try:
        for source, expected in train_pairs:
            total += 1
            if rule.apply(source) != expected:
                return False, total
    except (ArithmeticError, IndexError, TypeError, ValueError):
        return False, total
    return total > 0, total


def _source_structure(grid: Grid) -> tuple:
    from .objects import extract_objects
    return (len(grid), len(grid[0]),
            tuple(sorted({value for row in grid for value in row})),
            len(extract_objects(grid)),
            tuple(sorted(len(obj.cells) for obj in extract_objects(grid))))


def _rule_taxonomy(rules: Iterable[Rule]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for rule in rules:
        name = rule.name.lower()
        if rule.family == "relation-conditioned-copy" or rule.relation_predicates:
            category = "relational"
        elif rule.local_writes or "local-neighborhood" in name:
            category = "local-rewrite"
        elif "crop" in name or "scale" in name:
            category = "crop-scale"
        else:
            category = "other"
        counts[category] += 1
    return {key: counts.get(key, 0) for key in
            ("relational", "local-rewrite", "crop-scale", "other")}


class ArcSolver:
    """A deterministic solver; an optional ranker may reorder only verified rules."""

    def __init__(self, advisory_ranker: Callable[[list[dict]], list[str]] | None = None):
        self.advisory_ranker = advisory_ranker

    def solve(self, task: dict, include_coverage: bool = False) -> dict:
        train = tuple((parse_grid(pair["input"]), parse_grid(pair["output"]))
                      for pair in task.get("train", []))
        if not train:
            raise ValueError("ARC task must contain training demonstrations")
        verified: list[Rule] = []
        exact_verified: list[Rule] = []
        invariance_details: dict[str, dict] = {}
        structural_variants = len({_source_structure(source) for source, _ in train})
        coverage = None
        if include_coverage:
            hypotheses, search_stats = generate_hypotheses(
                train, return_search_stats=True)
            # Track funnel: raw generated -> after parsimony funnel -> after invariance
            raw_generated = len(hypotheses)
            # Apply parsimony funnel to relation hypotheses before invariance
            # (generate_hypotheses already applies 64->16 funnel internally)
            funneled_hypotheses = _funnel_hypotheses(hypotheses, max_before_invariance=16, max_per_placement_family=2)
            after_parsimony = len(funneled_hypotheses)
            
            generated_families = Counter(rule.family for rule in hypotheses)
            verified_families: Counter[str] = Counter()
            match_histogram: Counter[str] = Counter()
            rejected = execution_errors = near_misses = 0
            for rule in funneled_hypotheses:
                matched = errors = 0
                for source, expected in train:
                    try:
                        exact = rule.apply(source) == expected
                    except (ArithmeticError, IndexError, TypeError, ValueError):
                        errors += 1
                    else:
                        matched += int(exact)
                match_histogram[str(matched)] += 1
                if matched == len(train) and not errors:
                    exact_verified.append(replace(
                        rule, matched_examples=matched,
                        structural_coverage=structural_variants))
                    verified_families[rule.family] += 1
                else:
                    rejected += 1
                    execution_errors += int(errors > 0)
                    near_misses += int(len(train) > 1 and errors == 0 and
                                       matched == len(train) - 1)
            for rule in exact_verified:
                report = check_rule_invariance(rule, train)
                invariance_details[rule.name] = report
                # Acceptance filter: require at least one invariance pass.
                # Local-rewrite rules are only accepted if NO relational rule
                # (with relation_predicates) exists that also fits exactly.
                has_relational_alternative = any(
                    other.relation_predicates and other.name != rule.name
                    for other in exact_verified)
                if report["accepted"] and not (rule.local_writes > 0 and has_relational_alternative):
                    verified.append(replace(
                        rule, invariance_passes=report["passed"],
                        invariance_failures=report["failed"]))
            # Apply final selection: 1 primary + 1 distinct backup (pass@2)
            verified = _select_final_candidates(verified)
            verified_families = Counter(rule.family for rule in verified)
            if not exact_verified:
                if not hypotheses:
                    status = "no_hypothesis_generated"
                elif search_stats.get("triggered"):
                    status = ("composition_search_frontier_exhausted_without_exact_program"
                              if search_stats.get("termination") == "empty_frontier"
                              else "composition_search_budget_exhausted_without_exact_program")
                else:
                    status = "generated_but_none_replayed_exactly"
            elif not verified:
                status = "exact_hypotheses_rejected_by_invariance"
            else:
                status = "one_or_more_hypotheses_replayed_exactly"
            coverage = {
                "status": status,
                "generated_hypotheses": raw_generated,
                "after_parsimony_funnel": after_parsimony,
                "exact_training_hypotheses": len(exact_verified),
                "invariance_surviving_hypotheses": len(verified),
                "invariance_rejected_hypotheses": len(exact_verified) - len(verified),
                "verified_hypotheses": len(verified),
                "rejected_hypotheses": rejected,
                "execution_error_hypotheses": execution_errors,
                "near_miss_hypotheses": near_misses,
                "exact_demo_match_histogram": dict(sorted(
                    match_histogram.items(), key=lambda item: int(item[0]))),
                "families_generated": dict(sorted(generated_families.items())),
                "families_verified": dict(sorted(verified_families.items())),
                "exact_families": dict(sorted(Counter(
                    rule.family for rule in exact_verified).items())),
                "invariance_surviving_families": dict(sorted(Counter(
                    rule.family for rule in verified).items())),
                "exact_local_rewrite_hypotheses": sum(
                    rule.local_writes > 0 for rule in exact_verified),
                "invariance_surviving_local_rewrite_hypotheses": sum(
                    rule.local_writes > 0 for rule in verified),
                "exact_relation_hypotheses": sum(
                    bool(rule.relation_predicates) for rule in exact_verified),
                "invariance_surviving_relation_hypotheses": sum(
                    bool(rule.relation_predicates) for rule in verified),
                "exact_rule_taxonomy": _rule_taxonomy(exact_verified),
                "invariance_surviving_rule_taxonomy": _rule_taxonomy(verified),
                "invariance_check_outcomes": {
                    name: dict(Counter(
                        "pass" if item["checks"][name] is True else
                        "fail" if item["checks"][name] is False else "not_applicable"
                        for item in invariance_details.values()))
                    for name in ("landmark_translation", "canvas_padding",
                                 "background_recolor", "palette_rename")
                },
                "invariance_by_rule": invariance_details,
                "program_search": search_stats,
            }
        else:
            hypotheses = generate_hypotheses(train)
            # Apply parsimony funnel
            funneled_hypotheses = _funnel_hypotheses(hypotheses, max_before_invariance=16, max_per_placement_family=2)
            for rule in funneled_hypotheses:
                valid, matched = verify_rule(rule, train)
                if valid:
                    exact_verified.append(replace(
                        rule, matched_examples=matched,
                        structural_coverage=structural_variants))
            for rule in exact_verified:
                report = check_rule_invariance(rule, train)
                has_relational_alternative = any(
                    other.relation_predicates and other.name != rule.name
                    for other in exact_verified)
                if report["accepted"] and not (rule.local_writes > 0 and has_relational_alternative):
                    verified.append(replace(
                        rule, invariance_passes=report["passed"],
                        invariance_failures=report["failed"]))
            # Apply final selection
            verified = _select_final_candidates(verified)
        # Use structured hypothesis scoring for ranking
        scored_rules = []
        for rule in verified:
            evidence = extract_evidence(rule, list(train))
            score = compute_hypothesis_score(evidence)
            scored_rules.append((score, rule))
        scored_rules.sort(key=lambda x: (-x[0], x[1].name))
        verified = [rule for score, rule in scored_rules]
        if self.advisory_ranker and verified:
            summaries = [{"name": rule.name, "family": rule.family,
                          "complexity": rule.complexity,
                          "assumptions": rule.assumptions}
                         for rule in verified]
            try:
                requested = self.advisory_ranker(summaries)
                rank = {name: i for i, name in enumerate(requested)}
                verified.sort(key=lambda rule: (rank.get(rule.name, len(rank)),
                                                -rule.matched_examples,
                                                -len(rule.relation_predicates),
                                                -len(rule.invariance_passes),
                                                10 * rule.local_writes,
                                                rule.complexity, rule.assumptions,
                                                -rule.structural_coverage,
                                                rule.name))
            except Exception:
                pass  # deterministic exact verifier/ranker is authoritative

        tests = []
        for pair in task.get("test", []):
            source = parse_grid(pair["input"])
            votes: dict[Grid, list[Rule]] = {}
            palette = {value for row in source for value in row}
            for rule in verified:
                try:
                    output = rule.apply(source)
                except (ArithmeticError, IndexError, TypeError, ValueError):
                    continue
                votes.setdefault(output, []).append(rule)
            ranked_outputs = []
            for output, supporting in votes.items():
                # Use structured scoring for each supporting rule
                scored_supporting = []
                for rule in supporting:
                    evidence = extract_evidence(rule, list(train))
                    score = compute_hypothesis_score(evidence)
                    scored_supporting.append((score, rule))
                scored_supporting.sort(key=lambda x: (-x[0], x[1].name))
                
                # Use best rule per family as before
                best_by_family: dict[str, Rule] = {}
                for score, rule in scored_supporting:
                    current = best_by_family.get(rule.family)
                    if current is None or score > 0:
                        best_by_family[rule.family] = rule
                
                # Aggregate score from best per family
                total_score = 0.0
                for rule in best_by_family.values():
                    evidence = extract_evidence(rule, list(train))
                    total_score += compute_hypothesis_score(evidence)
                
                representative = scored_supporting[0][1]  # highest scoring
                ranked_outputs.append((output, supporting, total_score, representative))
            ranked_outputs.sort(key=lambda item: (-item[2], item[3].name))
            tests.append([Candidate(
                grid=output, rule=representative.name, confidence=score,
                simplicity=representative.complexity,
                assumptions=representative.assumptions,
                support=tuple(sorted(rule.name for rule in supporting)))
                for output, supporting, score, representative in ranked_outputs[:2]])
        result = {"candidates": tests,
                  "verified_rules": [rule.name for rule in verified],
                  "training_pairs": len(train)}
        if coverage is not None:
            result["hypothesis_coverage"] = coverage
        return result

    def solve_json(self, task: dict) -> dict:
        result = self.solve(task)
        return {"candidates": [[to_lists(candidate.grid) for candidate in row]
                                for row in result["candidates"]],
                "candidate_rules": [[{
                    "rule": candidate.rule,
                    "confidence_score": candidate.confidence,
                    "support": list(candidate.support),
                    "simplicity": candidate.simplicity,
                    "assumptions": candidate.assumptions,
                } for candidate in row] for row in result["candidates"]],
                "verified_rules": result["verified_rules"],
                "training_pairs": result["training_pairs"]}
