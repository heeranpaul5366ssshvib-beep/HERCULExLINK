"""Deterministic test doubles for semantic capability tests.

SemanticMockModel maps goal substrings to canned JSON payloads (or
failures). It simulates a model for plumbing/merge/validation tests —
never production behavior. Live-model coverage is env-gated elsewhere.
"""

import json


class SemanticMockModel:
    def __init__(self, script=None, default="[]", fail_with=None, fail_times=0,
                 model_name="mock-semantic-v1"):
        # script: [(substring, payload)] first match wins; payload may be
        # a dict/list (JSON-encoded) or a raw string (for malformed tests).
        self.script = list(script or [])
        self.default = default
        self.fail_with = fail_with
        self.fail_times = fail_times
        self.calls = 0
        self.prompts = []
        self.default_model = model_name

    def generate(self, prompt, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.fail_with or RuntimeError("mock model failure")
        for substring, payload in self.script:
            if substring in prompt:
                if isinstance(payload, str):
                    return payload
                return json.dumps(payload)
        if isinstance(self.default, str) and self.default.startswith("{"):
            return self.default
        if isinstance(self.default, str):
            return self.default
        return json.dumps(self.default)


def payload(*entries):
    return {"capabilities": list(entries)}


def entry(name, confidence=0.9, reason="mock", required=True, **extra):
    item = {"name": name, "confidence": confidence, "reason": reason, "required": required}
    item.update(extra)
    return item
