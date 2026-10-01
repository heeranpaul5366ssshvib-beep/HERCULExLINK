from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Reference Resolution (v1.1 upgrade layer)
Author: Heeran Paul
License: MIT
--------------------------------------------

Safe anaphoric reference resolution between task steps.

Pipeline position (authoritative)::

    USER REQUEST -> PLAN -> REFERENCE RESOLUTION -> PLAN VALIDATION
        -> CAPABILITY RESOLUTION -> EXECUTION

The resolver rewrites step descriptions only. It never executes tools,
never grants capabilities or permissions, never touches policy, and
never skips validation: resolved plans re-enter the existing
``validate_plan`` gate unchanged. Unresolvable or unsafe references
return structured errors (no execution).

Resolution sources (in order):
  * explicit file mentions in previous steps of the same plan
  * ``verified_artifacts`` from task context (durable, verified paths)
  * ``step_outputs`` from task context (previous verified outputs)
  * ``variables`` (named task variables holding file paths)

A reference resolves only when exactly one candidate exists.
Zero candidates -> UNRESOLVED_REFERENCE. Multiple -> AMBIGUOUS_REFERENCE
with candidates listed. References to explicitly unverified outputs ->
UNVERIFIED_REFERENCE. Any candidate or resolved path escaping the file
workspace sandbox -> REFERENCE_SANDBOX_VIOLATION. All errors abort
execution (caller must not execute).
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# File mentions: same shape FileAbility understands (plus common extras).
_FILE_RE = re.compile(
    r"""["']?((?:[\w\-.]+[\\/])*[\w\-.]*\.[\w\-.]+(?:\.[\w\-.]+)*)["']?""",
)
_SAFE_EXTS = {
    "txt", "md", "json", "py", "log", "csv",
    "yaml", "yml", "toml", "ini", "cfg", "js", "ts",
    "html", "css", "xml",
}

# Anaphoric phrases (case-insensitive). Standalone "that"/"this" are
# included because task steps say "use that" / "run it". Note: "read it
# back" is handled via the generic "it" match so the verb and "back"
# survive substitution ("read test.py back", not bare "test.py").
# Simpler authoritative pattern (word-level, avoids double alternation bugs).
_REF_WORD_RE = re.compile(
    r"(?i)\b(that\s+file|this\s+file|the\s+file"
    r"|that\s+result|this\s+result|the\s+result"
    r"|that\s+output|this\s+output|the\s+output"
    r"|it|that|this)\b"
)

_FILE_LIKE_RE = re.compile(r"^[\w\-.\\/]+$")

# Generic file requests ("read this file") carry no antecedent and must
# keep their legacy behavior: with zero prior artifacts they pass through
# unchanged for downstream validation/execution (echo providers, honest
# file-not-found). Only bare anaphora ("it", "that", "the result") with
# zero candidates is an unresolved reference. This preserves frozen v1.0
# contract behavior while still improving anaphoric chains.
_GENERIC_FILE_RE = re.compile(
    r"(?i)\b(that\s+file|this\s+file|the\s+file)\b"
)
_BARE_ANAPHORA_RE = re.compile(
    r"(?i)\b(it|that|this|that\s+result|this\s+result|the\s+result"
    r"|that\s+output|this\s+output|the\s+output)\b"
)

# Same-step result wording: "Calculate 19*23 and report the result". The
# result/output belongs to THIS step's own computation, not to a prior
# artifact; with zero prior candidates it must pass through (downstream
# planning/execution handle it) instead of failing the plan contract.
_SAME_STEP_RESULT_RE = re.compile(
    r"(?i)\b(?:calculate|compute|evaluate|determine|find|run|execute|check|"
    r"verify|make|produce|generate|return|give|report|show|display)\b"
    r"[^.]{0,120}?\b(?:the|that|this)\s+(?:result|output)\b")


def _is_generic_file_request(text: str) -> bool:
    """True for legacy generic file wording with no bare pronoun."""
    lowered = str(text or "")
    if not _GENERIC_FILE_RE.search(lowered):
        return False
    # Strip the generic file phrases; if bare anaphora remains ("it",
    # "that", "the result"), it still needs a prior antecedent.
    stripped = _GENERIC_FILE_RE.sub(" ", lowered)
    return not _BARE_ANAPHORA_RE.search(stripped)


# Object nouns that keep this/that anaphoric even in determiner position
# ("that file", "this result"), and particles that keep a following
# pronoun standalone ("read it back", "verify it now").
_ANAPHOR_OBJECT_NOUNS = {"file", "result", "output"}
_ANAPHOR_PARTICLES = {"back", "now", "again", "then", "out", "up",
                      "first", "please", "in", "there"}

# Conversational determiner usage: "research this topic", "remember that
# Paris is the capital". The pronoun names a content noun, not a task
# artifact, so it is prose and must pass through untouched.
_DETERMINER_NOUN_RE = re.compile(r"(?i)\b(this|that)\s+([a-z][a-z0-9_]*)")
_BARE_THIS_THAT_RE = re.compile(r"(?i)\b(this|that)\b")
_BARE_IT_RE = re.compile(r"(?i)\bit\b")

# Task action verbs that make a bare pronoun a file/task reference
# ("read it", "run it", "use that") rather than conversation.
_ANAPHOR_VERB_RE = re.compile(
    r"(?i)\b(create|write|read|run|execute|open|save|list|delete|"
    r"calculate|compute|show|display|verify|check|make|use)\b")


def _has_standalone_bare_pronoun(text: str) -> bool:
    """True when 'it' appears, or 'this/that' is used standalone.

    'this/that' directly followed by a content noun ("this topic") is
    determiner prose, not a task reference; followed by an anaphor object
    noun ("that file") or a particle ("that out") it stays anaphoric.
    """
    text = str(text or "")
    if _BARE_IT_RE.search(text):
        return True
    determiner_spans = set()
    for match in _DETERMINER_NOUN_RE.finditer(text):
        noun = match.group(2).lower()
        if noun in _ANAPHOR_OBJECT_NOUNS or noun in _ANAPHOR_PARTICLES:
            continue
        determiner_spans.add(match.span(1))
    for match in _BARE_THIS_THAT_RE.finditer(text):
        if match.span() not in determiner_spans:
            return True
    return False


def _contains_reference(text: str) -> bool:
    """True when text holds a file/task reference the resolver must handle.

    Explicit file phrases ("that file") and result/output phrases ("the
    result") are always references. Bare pronouns count only when used
    standalone ("read it", "run it", "use that") with a task action
    verb. Determiner prose ("research this topic") and verb-less chatter
    ("it is raining") are conversation, never file references: they pass
    through unchanged instead of failing the plan contract.
    """
    text = str(text or "")
    if _GENERIC_FILE_RE.search(text):
        return True
    if re.search(r"(?i)\b(?:that|this|the)\s+(?:result|output)\b", text):
        return True
    return (_has_standalone_bare_pronoun(text)
            and _ANAPHOR_VERB_RE.search(text) is not None)

# Verbs that start a new file action after a comma ("Create a.py, write ...").
_ACTION_VERBS = (
    "create", "write", "read", "run", "execute", "open", "save",
    "list", "delete", "calculate", "compute", "show", "display",
    "verify", "check", "make",
)
_COMMA_VERB_RE = re.compile(
    r",\s*(?=(" + r"|".join(_ACTION_VERBS) + r")\b)", re.IGNORECASE
)


class ReferenceResolutionError(ValueError):
    """Structured reference failure (caller must not execute)."""

    def __init__(self, code: str, detail: str = "", step_id: str = "",
                 candidates: Optional[List[str]] = None):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.step_id = step_id
        self.candidates = list(candidates or [])

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "step_id": self.step_id,
            "candidates": list(self.candidates),
        }


def extract_file_mentions(text: str) -> List[str]:
    """Explicit file paths mentioned in text (order-preserved, deduped)."""
    out: List[str] = []
    for match in _FILE_RE.finditer(str(text or "")):
        # Strip quotes/spaces and trailing sentence punctuation only.
        # Leading dots/slashes are preserved so "../evil" stays visible
        # for the sandbox check (never silently normalized to safe).
        raw = match.group(1).strip().strip("\"'").rstrip(".,;:!?").strip()
        if not raw or raw.lower() in {"it", "that", "this"}:
            continue
        # Must contain a dot + plausible extension to avoid matching
        # plain words ("back", "program").
        if "." not in raw:
            continue
        ext = raw.rsplit(".", 1)[-1].lower()
        # Allow dotted names like "test.py" but reject sentence fragments
        # ("it. Then", "back. And").
        if not ext or len(ext) > 5 or not ext.isalnum():
            continue
        if ext not in _SAFE_EXTS:
            continue
        # Reject matches that are really version numbers / decimals.
        head = raw.rsplit(".", 1)[0]
        if not head or not re.search(r"[A-Za-z0-9_\-]", head):
            continue
        if raw not in out:
            out.append(raw)
    return out


def _workspace_root() -> Path:
    """Sandbox root used for traversal checks (frozen-aware)."""
    try:
        from system.paths import is_frozen, user_data_dir
        if is_frozen():
            ws = user_data_dir() / "workspace"
            return ws.resolve() if ws.exists() else ws
    except Exception:
        pass
    try:
        return Path.cwd().resolve()
    except Exception:
        return Path.cwd()


def is_safe_workspace_path(candidate: str, workspace: Optional[Path] = None) -> bool:
    """True when candidate stays inside the file workspace sandbox."""
    text = str(candidate or "").strip().strip("\"'").strip()
    if not text:
        return False
    # Absolute Windows/posix paths are never auto-adopted via reference.
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\"):
        return False
    if text.startswith("/") and len(text) > 1:
        # A leading "/" with more path is an absolute escape; a bare
        # filename never starts with "/".
        return False
    # Explicit parent traversal is rejected (sandbox escape).
    parts = re.split(r"[\\/]+", text)
    if any(p == ".." for p in parts):
        return False
    if workspace is None:
        workspace = _workspace_root()
    try:
        base = workspace.resolve() if workspace.exists() else workspace
        target = (base / text).resolve() if not Path(text).is_absolute() else Path(text).resolve()
        target.relative_to(base)
        return True
    except Exception:
        return False


def workspace_relative(candidate: str, workspace: Optional[Path] = None) -> Optional[str]:
    """Workspace-relative form of a reference, or None when it escapes.

    The world model records absolute file paths while the reference
    gate only adopts workspace-relative wording. An absolute path that
    resolves INSIDE the workspace is folded to its relative form so
    verified cross-task artifacts stay usable; anything outside (or
    unresolvable) yields None and the caller still refuses honestly.
    """
    text = str(candidate or "").strip().strip("\"'").strip()
    if not text:
        return None
    if workspace is None:
        workspace = _workspace_root()
    try:
        base = workspace.resolve() if workspace.exists() else workspace
        target = (base / text).resolve() if not Path(text).is_absolute() else Path(text).resolve()
        rel = target.relative_to(base)
        return rel.as_posix()
    except Exception:
        return None


def split_compound_steps(step_texts: List[str]) -> List[str]:
    """Split comma-joined multi-action steps (conservative, deterministic).

    Only splits on commas followed by a file-action verb outside quotes,
    so "Calculate 25 times 4, please" and "Hi, how are you" stay intact.
    Trailing commas/periods are stripped. Empty fragments are dropped.
    """
    out: List[str] = []
    for raw in step_texts or []:
        text = str(raw or "")
        # Protect quoted spans ("HERCULE", 'data') from comma splitting.
        protected: List[str] = []
        def _stash(match: re.Match) -> str:
            protected.append(match.group(0))
            return f"\x00{len(protected) - 1}\x00"
        shielded = re.sub(r"'[^']*'|\"[^\"]*\"", _stash, text)
        parts = _COMMA_VERB_RE.split(shielded)
        # re.split with a group keeps separators; rebuild fragments.
        fragments: List[str] = []
        current = ""
        # _COMMA_VERB_RE has one capture group (the verb); splitting
        # yields [frag, verb, frag, verb, frag...]. Rejoin verb to next frag.
        tokens = _COMMA_VERB_RE.split(shielded)
        # Manual walk: split positions are commas; tokens alternate.
        # Simpler: use finditer to cut at comma boundaries.
        cuts = [m.start() for m in _COMMA_VERB_RE.finditer(shielded)]
        if not cuts:
            fragments = [shielded]
        else:
            prev = 0
            for cut in cuts:
                fragments.append(shielded[prev:cut])
                prev = cut + 1  # skip the comma itself
            fragments.append(shielded[prev:])
        for frag in fragments:
            # Restore quoted spans.
            def _restore(match: re.Match) -> str:
                try:
                    return protected[int(match.group(1))]
                except Exception:
                    return match.group(0)
            frag = re.sub(r"\x00(\d+)\x00", _restore, frag).strip().strip(",").strip()
            frag = frag.rstrip(".").strip()
            if frag:
                out.append(frag)
    return out or [str(s) for s in (step_texts or [])]


def _requires_resolution(text: str) -> bool:
    """Strict reference flavor that MUST resolve before execution.

    True for an explicit result/output phrase ("show the result") or a
    standalone bare pronoun used with a task action verb ("read it",
    "run it", "use that"). Conversational prose (no verb or determiner
    noun usage) never requires resolution.
    """
    text = str(text or "")
    if re.search(r"(?i)\b(?:that|this|the)\s+(?:result|output)\b", text):
        return True
    return (_has_standalone_bare_pronoun(text)
            and _ANAPHOR_VERB_RE.search(text) is not None)


def _context_artifacts(context: Optional[Dict[str, Any]]) -> Tuple[List[str], Dict[str, bool]]:
    """Ordered verified artifacts + per-artifact verified flag."""
    ctx = dict(context or {})
    ordered: List[str] = []
    verified: Dict[str, bool] = {}

    def _add(value: Any, is_verified: bool) -> None:
        if value is None:
            return
        items = value if isinstance(value, (list, tuple)) else [value]
        for item in items:
            name = str(item or "").strip().strip("\"'").rstrip(".,;:!?").strip()
            if not name or name in ordered:
                # Keep first-seen order; an explicitly unverified entry
                # downgrades a previously seen name to unverified.
                if name and not is_verified:
                    verified[name] = False
                continue
            ordered.append(name)
            verified[name] = bool(is_verified)

    for key in ("verified_artifacts", "verified_files", "artifacts"):
        _add(ctx.get(key), True)
    _add(ctx.get("unverified_artifacts"), False)
    _add(ctx.get("unverified_files"), False)
    # World-model entities (v2): fresh, verified names only. The
    # reference_candidates() helper already excludes stale and
    # inferred entries, so world names join as verified candidates.
    try:
        world = ctx.get("world")
        if world is not None and hasattr(world, "reference_candidates"):
            _add(world.reference_candidates(), True)
    except Exception:
        pass
    outputs = ctx.get("step_outputs") or ctx.get("previous_outputs") or {}
    if isinstance(outputs, dict):
        for _sid, oval in outputs.items():
            _add(oval, bool((ctx.get("verified_step_ids") is None) or
                            (str(_sid) in set(map(str, ctx.get("verified_step_ids") or [])))
                            or ctx.get("outputs_verified", True)))
    elif isinstance(outputs, (list, tuple)):
        for oval in outputs:
            _add(oval, bool(ctx.get("outputs_verified", True)))
    variables = ctx.get("variables") or ctx.get("task_variables") or {}
    if isinstance(variables, dict):
        for _k, vval in variables.items():
            text = str(vval or "")
            files = extract_file_mentions(text)
            if files:
                for found in files:
                    _add(found, True)
            elif _FILE_LIKE_RE.match(text.strip()) and "." in text:
                _add(text.strip(), True)
    return ordered, verified


def _substitute(text: str, replacement: str) -> str:
    """Replace anaphoric phrases with the resolved artifact name."""
    def _repl(match: re.Match) -> str:
        original = match.group(0)
        # Preserve leading capital ("That file" -> "Test.py" stays "test.py";
        # filenames are case-sensitive on disk, so keep exact candidate).
        return replacement
    return _REF_WORD_RE.sub(_repl, str(text or ""))


def resolve_step_texts(
    step_texts: List[str],
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """Resolve references in raw step strings (Brain pre-plan stage).

    Returns (resolved_texts, report). Raises ReferenceResolutionError on
    ambiguous/unresolved/unverified/sandbox failures (caller must not
    execute).
    """
    texts = list(step_texts or [])
    ctx_ordered, ctx_verified = _context_artifacts(context)
    known: List[str] = list(ctx_ordered)
    known_verified: Dict[str, bool] = dict(ctx_verified)
    resolved: List[str] = []
    resolutions: List[Dict[str, Any]] = []

    for index, raw in enumerate(texts):
        text = str(raw or "")
        if not _contains_reference(text):
            for found in extract_file_mentions(text):
                if found not in known:
                    known.append(found)
                    known_verified.setdefault(found, True)
            resolved.append(text)
            continue
        # Candidates: context artifacts + files from previous steps +
        # files mentioned earlier in THIS step (intra-step "Create a.py,
        # write into it").
        prefix_files: List[str] = []
        # Find reference positions to allow intra-step prefix matching.
        ref_positions = [m.start() for m in _REF_WORD_RE.finditer(text)]
        file_positions = [(m.start(), m.group(1)) for m in _FILE_RE.finditer(text)]
        first_ref = min(ref_positions) if ref_positions else len(text)
        for pos, name in file_positions:
            clean = str(name).strip().strip("\"'").rstrip(".,;:!?").strip()
            if pos < first_ref and clean and clean not in prefix_files:
                # Validate extension like extract_file_mentions does.
                if "." in clean and clean.rsplit(".", 1)[-1].lower() in _SAFE_EXTS:
                    prefix_files.append(clean)
        candidates: List[str] = []
        for cand in list(known) + [f for f in prefix_files if f not in known]:
            if cand not in candidates:
                candidates.append(cand)
        step_id = f"step-{index + 1}"
        if not candidates:
            # Legacy generic file wording ("read this file") with no prior
            # passes through for downstream handling (preserves v1.0), as
            # does conversational prose that carries no task anaphor
            # (determiner nouns, verb-less chatter) and same-step result
            # wording ("Calculate X and report the result") whose referent
            # is the step's own computation.
            if (_is_generic_file_request(text) or not _requires_resolution(text)
                    or _SAME_STEP_RESULT_RE.search(text)):
                for found in extract_file_mentions(text):
                    if found not in known:
                        known.append(found)
                        known_verified.setdefault(found, True)
                resolved.append(text)
                continue
            raise ReferenceResolutionError(
                "UNRESOLVED_REFERENCE",
                f"{step_id} contains an anaphoric reference but no prior file, output, or variable names it",
                step_id=step_id, candidates=[])
        # Distinct candidates -> ambiguous (never guess).
        distinct = list(dict.fromkeys(candidates))
        if len(distinct) > 1:
            raise ReferenceResolutionError(
                "AMBIGUOUS_REFERENCE",
                f"{step_id} reference matches multiple objects; clarify which one",
                step_id=step_id, candidates=distinct)
        winner = distinct[0]
        if known_verified.get(winner) is False:
            raise ReferenceResolutionError(
                "UNVERIFIED_REFERENCE",
                f"{step_id} refers to unverified output '{winner}'; verify it first",
                step_id=step_id, candidates=[winner])
        # World-recorded absolute paths inside the workspace fold to
        # their relative form; anything escaping still refuses honestly.
        _folded = workspace_relative(winner)
        if _folded is None:
            raise ReferenceResolutionError(
                "REFERENCE_SANDBOX_VIOLATION",
                f"{step_id} reference '{winner}' escapes the file workspace sandbox",
                step_id=step_id, candidates=[winner])
        winner = _folded
        if not is_safe_workspace_path(winner):
            raise ReferenceResolutionError(
                "REFERENCE_SANDBOX_VIOLATION",
                f"{step_id} reference '{winner}' escapes the file workspace sandbox",
                step_id=step_id, candidates=[winner])
        new_text = _substitute(text, winner)
        if not is_safe_workspace_path(winner):
            raise ReferenceResolutionError(
                "REFERENCE_SANDBOX_VIOLATION",
                f"{step_id} resolved path escapes the sandbox",
                step_id=step_id, candidates=[winner])
        resolutions.append({"step_id": step_id, "from": text[:160],
                            "to": new_text[:160], "resolved": winner})
        for found in extract_file_mentions(new_text):
            if found not in known:
                known.append(found)
                known_verified.setdefault(found, True)
        resolved.append(new_text)
    return resolved, {"ok": True, "resolutions": resolutions,
                      "code": "REFERENCES_RESOLVED" if resolutions else "NO_REFERENCES"}


def resolve_plan_references(
    plan: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Resolve references in a capable plan (dict steps).

    Rewrites description/objective/goal + refreshes required_capabilities
    and verification_criteria from the resolved text so the existing
    contract/validation gates judge the executable wording. All other
    step fields (ids, dependencies, risk, timeouts, inputs) are preserved;
    mapping ``inputs`` values containing references are resolved too.

    Returns (resolved_plan, report). Raises ReferenceResolutionError
    (caller must not execute).
    """
    steps = [dict(s) for s in (plan or [])]
    ctx_ordered, ctx_verified = _context_artifacts(context)
    known: List[str] = list(ctx_ordered)
    known_verified: Dict[str, bool] = dict(ctx_verified)
    resolutions: List[Dict[str, Any]] = []

    for index, step in enumerate(steps):
        step_id = str(step.get("step_id", f"step-{index + 1}"))
        description = str(step.get("description", step.get("goal", step.get("objective", ""))) or "")
        inputs = step.get("inputs") if isinstance(step.get("inputs"), dict) else {}
        blob = description + " " + " ".join(str(v) for v in (inputs or {}).values())
        if not _contains_reference(blob):
            for found in extract_file_mentions(description):
                if found not in known:
                    known.append(found)
                    known_verified.setdefault(found, True)
            # Also learn file-valued inputs for later steps.
            for value in (inputs or {}).values():
                for found in extract_file_mentions(str(value)):
                    if found not in known:
                        known.append(found)
                        known_verified.setdefault(found, True)
            continue
        ref_positions = [m.start() for m in _REF_WORD_RE.finditer(description)]
        first_ref = min(ref_positions) if ref_positions else len(description)
        prefix_files: List[str] = []
        for match in _FILE_RE.finditer(description):
            pos, name = match.start(), match.group(1)
            clean = str(name).strip().strip("\"'").rstrip(".,;:!?").strip()
            if pos < first_ref and clean and clean not in prefix_files:
                if "." in clean and clean.rsplit(".", 1)[-1].lower() in _SAFE_EXTS:
                    prefix_files.append(clean)
        candidates: List[str] = []
        for cand in list(known) + [f for f in prefix_files if f not in known]:
            if cand not in candidates:
                candidates.append(cand)
        if not candidates:
            if (_is_generic_file_request(description) or not _requires_resolution(description)
                    or _SAME_STEP_RESULT_RE.search(description)):
                for found in extract_file_mentions(description):
                    if found not in known:
                        known.append(found)
                        known_verified.setdefault(found, True)
                continue
            raise ReferenceResolutionError(
                "UNRESOLVED_REFERENCE",
                f"{step_id} contains an anaphoric reference but no prior file, output, or variable names it",
                step_id=step_id, candidates=[])
        distinct = list(dict.fromkeys(candidates))
        if len(distinct) > 1:
            raise ReferenceResolutionError(
                "AMBIGUOUS_REFERENCE",
                f"{step_id} reference matches multiple objects; clarify which one",
                step_id=step_id, candidates=distinct)
        winner = distinct[0]
        if known_verified.get(winner) is False:
            raise ReferenceResolutionError(
                "UNVERIFIED_REFERENCE",
                f"{step_id} refers to unverified output '{winner}'; verify it first",
                step_id=step_id, candidates=[winner])
        _folded = workspace_relative(winner)
        if _folded is None:
            raise ReferenceResolutionError(
                "REFERENCE_SANDBOX_VIOLATION",
                f"{step_id} reference '{winner}' escapes the file workspace sandbox",
                step_id=step_id, candidates=[winner])
        winner = _folded
        if not is_safe_workspace_path(winner):
            raise ReferenceResolutionError(
                "REFERENCE_SANDBOX_VIOLATION",
                f"{step_id} reference '{winner}' escapes the file workspace sandbox",
                step_id=step_id, candidates=[winner])
        new_description = _substitute(description, winner)
        step["description"] = new_description
        # Keep goal/objective consistent with the executable wording.
        if step.get("objective"):
            step["objective"] = _substitute(str(step.get("objective") or ""), winner)
        if step.get("goal"):
            step["goal"] = _substitute(str(step.get("goal") or ""), winner)
        if isinstance(step.get("inputs"), dict):
            step["inputs"] = {k: (_substitute(str(v), winner) if isinstance(v, str) and _contains_reference(str(v)) else v)
                              for k, v in step["inputs"].items()}
        # Refresh capabilities + verification from resolved wording so the
        # contract gate judges what will actually execute (validation
        # itself still runs downstream and can reject).
        try:
            from cognition.capabilities.inference import infer_capabilities
            from cognition.planner.capable import VERIFICATION_DEFAULTS
            from cognition.capabilities.capability import coerce_capability
            inferred = [c.value for c in infer_capabilities(new_description)]
            if inferred:
                step["required_capabilities"] = inferred
                criteria: List[str] = []
                for name in inferred:
                    try:
                        cap = coerce_capability(name)
                    except Exception:
                        cap = None
                    criteria.extend(VERIFICATION_DEFAULTS.get(cap, ["tool reported success"]) if cap is not None else ["tool reported success"])
                if criteria:
                    step["verification_criteria"] = criteria
        except Exception:
            pass
        resolutions.append({"step_id": step_id, "resolved": winner,
                            "to": new_description[:160]})
        for found in extract_file_mentions(new_description):
            if found not in known:
                known.append(found)
                known_verified.setdefault(found, True)
    return steps, {"ok": True, "resolutions": resolutions,
                   "code": "REFERENCES_RESOLVED" if resolutions else "NO_REFERENCES"}
