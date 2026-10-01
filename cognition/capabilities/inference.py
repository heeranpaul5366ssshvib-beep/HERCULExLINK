from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Capability Inference
Author: Heeran Paul
License: MIT
--------------------------------------------

Deterministic keyword inference: step text -> required capabilities.
Structured and testable; never LLM-generated strings. Retrieved /
untrusted content is treated as DATA — inference only matches
capability keywords and can never grant permissions or instructions.
"""

import re
from typing import Dict, List

from cognition.capabilities.capability import Capability

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

# Ordered by specificity: first match groups win ties deterministically.
_RULES: list[tuple[Capability, tuple[str, ...]]] = [
    (Capability.TERMINAL_EXECUTE, ("terminal", "shell", "command line", "run the test", "run tests", "pytest", "execute the test")),
    (Capability.CODE_EXECUTION, ("run the script", "execute the script", "run python", "execute code", "run code")),
    (Capability.CODE_EDIT, ("modify", "edit the code", "refactor", "patch the", "implement the function", "write code", "fix the bug in")),
    (Capability.FILE_WRITE, ("write the file", "create the file", "save the file", "create a file", "write a file", "create and validate")),
    (Capability.FILE_READ, ("read the file", "read this file", "open the file", "inspect the file", "show the file", "read file",
                           "list the files", "list files", "list the directory", "directory listing")),
    (Capability.DOCUMENT_WRITE, ("write the document", "draft the report", "create the document", "write the report")),
    (Capability.DOCUMENT_READ, ("read the document", "summarize the document", "review the document", "parse the document")),
    (Capability.KNOWLEDGE_RETRIEVAL, ("look up", "retrieve", "recall", "what do we know", "search memory", "knowledge base")),
    (Capability.WEB_SEARCH, ("search the web", "google", "research this topic", "research the", "look up online", "web search")),
    (Capability.BROWSER_USE, ("open the browser", "browse to", "click through", "navigate to", "open the page")),
    (Capability.DATABASE_WRITE, ("update the database", "insert into", "delete from the database", "write to the database")),
    (Capability.DATABASE_READ, ("query the database", "read from the database", "select from", "database lookup")),
    (Capability.VISION_ANALYSIS, ("screenshot", "analyze the image", "describe the picture", "visual inspection", "analyze the chart",
                                 "analyze this screen", "analyze the screen", "analyze my screen",
                                 "what is on my screen", "what's on my screen", "what does this image show",
                                 "describe the image", "describe this image", "explain this screenshot",
                                 "read this error", "describe what is on")),
    (Capability.SPEECH_RECOGNITION, ("transcribe", "speech to text", "dictation")),
    (Capability.TEXT_TO_SPEECH, ("read aloud", "text to speech", "synthesize speech", "narrate")),
    (Capability.SYSTEM_OBSERVE, ("check health", "system status", "system information", "show my system",
                                "monitor", "observe", "diagnose the system", "diagnostics")),
    (Capability.APPLICATION_CONTROL, ("restart the service", "control the app", "launch the application", "stop the service",
                                      "open notepad", "open calculator", "open the calculator",
                                      "into notepad", "in notepad", "notepad window",
                                      "click the", "click on", "double click", "right click", "type into", "press enter",
                                      "press the", "move the pointer", "move the mouse")),
    (Capability.MATH, ("calculate", "compute", "solve the equation", "arithmetic", "sum of", "average of")),
]

# Phrases that look like instructions but must never yield capabilities
# when they arrive inside untrusted content.
_INSTRUCTION_MARKERS = ("ignore previous", "disregard", "grant admin", "sudo", "override policy", "disable safety")

# Negation scope: a matched phrase is dropped when its sentence carries
# a negation marker before the phrase ("Do NOT modify the source").
_NEGATIONS = ("do not", "don't", "dont", "never", "without", "no ", "not ", "n't ", "refuse to", "avoid")


def _negated(lowered: str, sentences: List[str], hit_at: int) -> bool:
    """True when a negation marker precedes the match in its sentence."""
    offset = 0
    for sentence in sentences:
        start = lowered.find(sentence, offset)
        end = start + len(sentence)
        if start <= hit_at < end:
            before = sentence[: hit_at - start]
            return any(marker in before for marker in _NEGATIONS)
        offset = end
    head = lowered[max(0, hit_at - 40):hit_at]
    return any(marker in head for marker in _NEGATIONS)


def mark_untrusted(text: str) -> Dict[str, object]:
    """Wrap retrieved/external content as DATA, never instructions."""
    return {"data": str(text), "trusted": False}


def infer_capabilities(step: object) -> List[Capability]:
    """Infer required capabilities from a step description or mapping."""
    if isinstance(step, dict):
        text = str(step.get("description", "") or step.get("goal", ""))
        trusted = step.get("trusted", True)
    else:
        text = str(step)
        trusted = True
    lowered = text.lower()
    if not trusted and any(marker in lowered for marker in _INSTRUCTION_MARKERS):
        return []  # untrusted instruction injection yields nothing
    found: List[Capability] = []
    sentences = re.split(r"[.!?;\n]+", lowered)
    # Filename-anchored fallback: "read test.txt" / "create test.txt"
    # carry no word "file" but clearly name a file artifact.
    if re.search(r"\b[\w\-.]+\.(txt|md|json|py|log|csv)\b", lowered):
        if re.search(r"\bread\b|\bopen\b|\bshow\b|\bdisplay\b|\bcat\b", lowered):
            if Capability.FILE_READ not in found:
                found.append(Capability.FILE_READ)
        if re.search(r"\bcreate\b|\bwrite\b|\bsave\b|\bmake\b", lowered):
            if Capability.FILE_WRITE not in found:
                found.append(Capability.FILE_WRITE)
    for capability, phrases in _RULES:
        for phrase in phrases:
            hit_at = lowered.find(phrase)
            if hit_at < 0 or capability in found:
                continue
            if _negated(lowered, sentences, hit_at):
                continue  # "Do NOT modify ..." must not propose CODE_EDIT
            found.append(capability)
            break
    # "validate" alongside creation implies execution/verification tooling.
    if "validate" in lowered and Capability.FILE_WRITE in found and Capability.TERMINAL_EXECUTE not in found:
        tokens = set(_TOKEN_RE.findall(lowered))
        if {"project", "test", "suite", "run"} & tokens:
            found.append(Capability.TERMINAL_EXECUTE)
    return found
