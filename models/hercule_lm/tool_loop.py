from __future__ import annotations
"""Tool-use loop: generate -> <TOOL_CALL> -> execute -> <TOOL_RESULT> -> continue.

The model emits ``<TOOL_CALL>{"tool": "<name>", "arguments": {...}}</TOOL_CALL>``.
The loop parses it, executes via the ability manager (or an injected
tool table), appends ``<TOOL_RESULT>{...}</TOOL_RESULT>``, and resumes
generation. Stops on: final answer (no tool call), max iterations,
EOS, or error.

Usage:
    python -m models.hercule_lm.tool_loop --checkpoint <dir> --prompt "..."

Programmatic:
    from models.hercule_lm.tool_loop import run_tool_loop
    result = run_tool_loop(model, tokenizer, "Search the web for X",
                           tools={"search": SearchAbility()})
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TOOL_CALL_OPEN = "<TOOL_CALL>"
TOOL_CALL_CLOSE = "</TOOL_CALL>"
TOOL_RESULT_OPEN = "<TOOL_RESULT>"
TOOL_RESULT_CLOSE = "</TOOL_RESULT>"
TOOL_ERROR_OPEN = "<TOOL_ERROR>"
TOOL_ERROR_CLOSE = "</TOOL_ERROR>"

_CALL_RE = re.compile(
    re.escape(TOOL_CALL_OPEN) + r"(.*?)" + re.escape(TOOL_CALL_CLOSE),
    re.DOTALL,
)


def extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Parse the first <TOOL_CALL>{json}</TOOL_CALL> in text, or None."""
    match = _CALL_RE.search(text or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(1).strip())
    except Exception:
        return None
    if not isinstance(payload, dict) or "tool" not in payload:
        return None
    return {"tool": str(payload["tool"]),
            "arguments": payload.get("arguments", {}) or {},
            "raw": match.group(0)}


def format_tool_result(result: Any) -> str:
    try:
        body = json.dumps(result, ensure_ascii=False)[:4000]
    except Exception:
        body = str(result)[:4000]
    return f"{TOOL_RESULT_OPEN}{body}{TOOL_RESULT_CLOSE}"


def format_tool_error(error: str) -> str:
    return f"{TOOL_ERROR_OPEN}{str(error)[:500]}{TOOL_ERROR_CLOSE}"


def default_dispatcher(tools: Dict[str, Any]) -> Callable[[str, Dict], Any]:
    """Build a dispatcher over a {name: ability-or-callable} table."""
    def dispatch(tool: str, arguments: Dict) -> Any:
        if tool not in tools:
            raise ValueError(f"Unknown tool: {tool}")
        target = tools[tool]
        if callable(getattr(target, "execute", None)):
            return target.execute(**arguments) if isinstance(arguments, dict) \
                else target.execute(arguments)
        if callable(target):
            return target(**arguments) if isinstance(arguments, dict) \
                else target(arguments)
        raise TypeError(f"Tool {tool!r} is not executable")
    return dispatch


def manager_dispatcher(manager) -> Callable[[str, Dict], Any]:
    """Dispatcher over AbilityManager.execute (keeps permission gates)."""
    def dispatch(tool: str, arguments: Dict) -> Any:
        if isinstance(arguments, dict):
            return manager.execute(tool, **arguments)
        return manager.execute(tool, arguments)
    return dispatch


def run_tool_loop(model, tokenizer, prompt: str,
                  tools: Optional[Dict[str, Any]] = None,
                  dispatcher: Optional[Callable[[str, Dict], Any]] = None,
                  max_new_tokens: int = 64,
                  max_iterations: int = 3,
                  temperature: float = 0.0,
                  seed: int = 0,
                  stop_on_error: bool = False) -> Dict[str, Any]:
    """Run generate->tool->generate until a final answer or limits.

    Returns {"text": full transcript, "tool_calls": [...],
             "iterations": n, "stopped": reason}.
    """
    if dispatcher is None:
        dispatcher = default_dispatcher(tools or {})
    transcript = str(prompt)
    tool_calls: List[Dict[str, Any]] = []
    stopped = "final_answer"

    def _decode_keep_specials(tokenizer, ids: list) -> str:
        # Default decode(skip_specials=True) strips <TOOL_CALL> etc.,
        # which makes extract_tool_call() never match. Preserve them.
        try:
            return tokenizer.decode(ids, skip_specials=False)
        except TypeError:
            pass
        try:
            return tokenizer.decode_with_specials(ids)
        except Exception:
            pass
        return tokenizer.decode(ids)

    ctx = int(getattr(getattr(model, "config", None), "context_length", 0) or 0)

    for iteration in range(max_iterations + 1):
        prev_transcript = transcript
        ids = tokenizer.encode(transcript)
        # Model caps total length at context_length; a prompt longer
        # than context would otherwise yield zero new tokens silently.
        # Keep the tail so generation can proceed, warn on stderr.
        if ctx and len(ids) >= ctx:
            keep = max(1, ctx - max_new_tokens - 1)
            if len(ids) > keep:
                print(f"[tool-loop] prompt truncated: {len(ids)} -> {keep} "
                      f"(context_length={ctx})", file=sys.stderr)
                ids = ids[-keep:]
        out_ids = model.generate(list(ids), max_new_tokens=max_new_tokens,
                                 temperature=temperature, seed=seed)
        new_text = _decode_keep_specials(tokenizer, out_ids[len(ids):])
        if not new_text:
            stopped = "context_full" if (ctx and len(ids) >= ctx) else "final_answer"
            break
        transcript += new_text

        # Prompt may end with an open <TOOL_CALL> and the model only
        # completes the JSON + close tag, so the call can straddle the
        # prompt/generation boundary. Check new_text first, then bridge.
        call = extract_tool_call(new_text)
        if call is None:
            bridge = prev_transcript[-200:] + new_text
            bridged = extract_tool_call(bridge)
            # Only accept if the close tag came from new output
            # (avoids re-firing the few-shot example in the prompt).
            if bridged is not None and bridge.rfind(TOOL_CALL_CLOSE) >= len(prev_transcript[-200:]):
                call = bridged
        if call is None or iteration >= max_iterations:
            if call is not None:
                stopped = "max_iterations"
            break
        try:
            result = dispatcher(call["tool"], call["arguments"])
            transcript += format_tool_result(result)
            status = "ok"
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            transcript += format_tool_error(err)
            status = "error"
            if stop_on_error:
                stopped = "tool_error"
                tool_calls.append({**call, "status": status, "error": err})
                break
        tool_calls.append({**call, "status": status})

    return {"text": transcript, "tool_calls": tool_calls,
            "iterations": iteration + 1, "stopped": stopped}


def _load_default_tools():
    """Lazily build the default tool table (heavy imports deferred)."""
    from abilities.search.search_ability import SearchAbility

    try:
        from abilities.calculator.calculator_ability import CalculatorAbility
        calc = CalculatorAbility()
    except Exception:
        calc = None
    tools = {"search": SearchAbility()}
    if calc is not None:
        tools["calculator"] = calc
    return tools


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hercule-tool-loop")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tokenizer-dir", default="")
    parser.add_argument("--prompt", default="Search the web for the capital of France.")
    parser.add_argument("--prompt-file", default="",
                        help="Read prompt from a file (avoids shell quoting issues)")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(
            (Path(args.checkpoint) / "manifest.json").read_text(encoding="utf-8"))
        from .config import HerculeLMConfig
        config = HerculeLMConfig.from_dict(manifest["architecture"])
    except Exception as exc:
        print(f"CHECKPOINT_CORRUPTED: {exc}", file=sys.stderr)
        return 2
    tok_dir = args.tokenizer_dir or f"training/tokenizer/{config.tokenizer_id}"
    try:
        from .hf_tokenizer import load_hf_tokenizer
        tokenizer = load_hf_tokenizer(tok_dir)
    except Exception:
        from .tokenizer import HerculeBPETokenizer
        try:
            tokenizer = HerculeBPETokenizer.load(tok_dir)
        except Exception as exc:
            print(f"TOKENIZER_FAILURE: {exc}", file=sys.stderr)
            return 2
    from .model import HerculeLM
    from . import checkpoint as ckpt
    model = HerculeLM(config, seed=0)
    try:
        ckpt.load_checkpoint(args.checkpoint, model, strict=True)
    except Exception as exc:
        print(f"CHECKPOINT_MISMATCH: {exc}", file=sys.stderr)
        return 2

    prompt = args.prompt
    if args.prompt_file:
        try:
            # utf-8-sig strips the BOM PowerShell Set-Content adds;
            # fall back to utf-16 for `> file` redirection (UTF-16LE BOM).
            raw = Path(args.prompt_file).read_bytes()
            for enc in ("utf-8-sig", "utf-16", "utf-8"):
                try:
                    prompt = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                prompt = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"PROMPT_FAILURE: {exc}", file=sys.stderr)
            return 2
    if prompt.startswith("\ufeff"):
        prompt = prompt.lstrip("\ufeff")

    t0 = time.perf_counter()
    try:
        tools = _load_default_tools()
    except Exception as exc:
        print(f"TOOLS_FAILURE: {exc}", file=sys.stderr)
        return 2
    result = run_tool_loop(model, tokenizer, prompt, tools=tools,
                           max_new_tokens=args.max_new_tokens,
                           max_iterations=args.max_iterations,
                           temperature=args.temperature, seed=args.seed)
    print(result["text"])
    print(f"[iterations={result['iterations']} tool_calls={len(result['tool_calls'])} "
          f"stopped={result['stopped']} {(time.perf_counter()-t0)*1000:.0f}ms]",
          file=sys.stderr)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
