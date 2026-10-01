from __future__ import annotations
"""Phase G: research integration (UAI §23).

ResearchAbility runs the real ResearchEngine workflow through the
ability pipeline. No network is touched: scripted source doubles
stand in for web/search abilities. Honesty rules are absolute —
unreachable/empty/malformed sources yield ``unverified`` + ``[]``.
"""

import pytest

from abilities.ability_manager import AbilityManager
from abilities.research.research_ability import ResearchAbility
from security.permissions.policy_manager import PolicyManager


class _DictSource:
    """Scripted source double returning a fixed sources envelope."""

    def __init__(self, sources=None, error=None):
        self._sources = sources
        self._error = error

    def execute(self, topic, **kwargs):
        if self._error is not None:
            raise self._error
        return {"status": "success", "sources": self._sources}


def _manager_with_research(source=None):
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    abilities.register(ResearchAbility(source_ability=source))
    return abilities, policy


# 1. research request without a source is honest
def test_request_without_source_is_unverified():
    ability = ResearchAbility()
    out = ability.execute("anything at all")
    assert out["status"] == "success"  # workflow ran
    assert out["verification_status"] == "unverified"
    assert out["evidence"] == []
    assert out["sources"] == []
    assert out["error"] is None  # honest-success path: no failure occurred
    assert "no source material" in out["synthesis"].lower()


# 2. source discovery / late wiring
def test_attach_source_wires_discovery():
    ability = ResearchAbility()
    assert ability.execute("t")["evidence"] == []
    ability.attach_source(_DictSource(
        [{"url": "https://example.test/a", "content": "[FACT] alpha holds"}]))
    out = ability.execute("t")
    assert len(out["evidence"]) == 1
    assert out["sources"] == ["https://example.test/a"]


# 3. successful source collects labeled evidence
def test_successful_source_labels():
    ability = ResearchAbility(_DictSource([
        {"url": "u1", "content": "[FACT] Water boils at 100C at sea level"},
        {"url": "u2", "content": "Therefore the sample will boil near 100C"},
    ]))
    out = ability.execute("boiling point")
    assert out["status"] == "success"
    labels = [e["label"] for e in out["evidence"]]
    assert labels == ["FACT", "INFERENCE"]
    assert out["synthesis"] and "FACT" in out["synthesis"]


# 4. unavailable network (source raises) -> unverified, no fabrication
def test_unavailable_network_is_honest():
    ability = ResearchAbility(_DictSource(error=ConnectionError("offline")))
    out = ability.execute("anything")
    assert out["verification_status"] == "unverified"
    assert out["evidence"] == []
    assert out["sources"] == []


# 5. malformed source envelope -> unverified, no fabrication
def test_malformed_source_is_honest():
    class _Garbage:
        def execute(self, topic, **kwargs):
            return {"unexpected": object()}

    out = ResearchAbility(_Garbage()).execute("anything")
    assert out["verification_status"] == "unverified"
    assert out["evidence"] == []


# 6. empty result -> unverified
def test_empty_result_is_honest():
    out = ResearchAbility(_DictSource([])).execute("nothing to find")
    assert out["verification_status"] == "unverified"
    assert out["evidence"] == []
    assert "no source material" in out["synthesis"].lower()


# 7. multiple sources all surface with provenance
def test_multiple_sources_keep_provenance():
    ability = ResearchAbility(_DictSource([
        {"url": "a", "content": "[FACT] first claim here"},
        {"url": "b", "content": "[FACT] second claim here"},
        {"url": "c", "content": "plain unmarked material"},
    ]))
    out = ability.execute("topic")
    assert [e["source"] for e in out["evidence"]] == ["a", "b", "c"]
    assert out["sources"] == ["a", "b", "c"]


# 8. conflicting evidence is flagged, never silently merged
def test_conflicting_evidence_flagged():
    ability = ResearchAbility(_DictSource([
        {"url": "doc-a", "content": "[FACT] The library supports python 3.12"},
        {"url": "doc-b", "content": "[FACT] The library does not support python 3.12"},
    ]))
    out = ability.execute("compatibility")
    assert len(out["contradictions"]) == 1
    assert "doc-a" in out["contradictions"][0]
    assert out["verification_status"] == "unverified"  # contradictions block verified


# 9. verification semantics: 2+ clean facts verify, else not
def test_verification_semantics():
    clean = ResearchAbility(_DictSource([
        {"url": "a", "content": "[FACT] alpha element present here"},
        {"url": "b", "content": "[FACT] beta element present here"},
    ])).execute("t")
    assert clean["verification_status"] == "verified"
    assert clean["confidence"] > 0.5
    single = ResearchAbility(_DictSource(
        [{"url": "a", "content": "[FACT] lonely fact stated here"}])).execute("t")
    assert single["verification_status"] == "unverified"


# 10. ability-pipeline integration: policy + capabilities + validation
def test_pipeline_integration():
    abilities, policy = _manager_with_research()
    out = abilities.execute("research", "pipeline topic",
                            capabilities=["KNOWLEDGE_RETRIEVAL"])
    assert out["status"] == "success"
    assert out["verification_status"] == "unverified"  # no source attached
    # Empty topics are rejected before execution.
    with pytest.raises(RuntimeError, match="Invalid inputs"):
        abilities.execute("research", "   ",
                          capabilities=["KNOWLEDGE_RETRIEVAL"])
    # Policy denial is enforced at the pipeline, not bypassed by research.
    policy.set_permission("KNOWLEDGE_RETRIEVAL", False)
    try:
        with pytest.raises(RuntimeError, match="Permission denied"):
            abilities.execute("research", "pipeline topic",
                              capabilities=["KNOWLEDGE_RETRIEVAL"])
    finally:
        policy.set_permission("KNOWLEDGE_RETRIEVAL", True)
