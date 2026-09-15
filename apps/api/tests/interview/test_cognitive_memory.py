"""
@file test_cognitive_memory.py
@description Unit tests for CognitiveMemoryGraph and CompetencyNode.
"""

from realmock.domains.interview.agents.memory import (
    CognitiveMemoryGraph,
    CompetencyStatus,
    WorkingMemory,
)


def test_cognitive_graph_record_and_render():
    graph = CognitiveMemoryGraph()
    graph.record_finding(
        topic="MySQL-MVCC",
        category="database",
        status=CompetencyStatus.VERIFIED,
        claim="Explained undo log and read view visibility",
        finding="Demonstrated precise understanding of repeatable read isolation",
        turn_index=1,
        confidence=0.9,
    )
    graph.record_finding(
        topic="Raft-Election",
        category="distributed_systems",
        status=CompetencyStatus.SUSPICIOUS,
        claim="Claimed election timeout doesn't matter",
        finding="Failed to identify split vote issue",
        turn_index=2,
        confidence=0.4,
    )
    graph.working_memory.pending_probes.append("Dig deeper into split vote in Raft")

    summary = graph.render_prompt_summary()
    assert "[Cognitive Competency Assessment]" in summary
    assert "MySQL-MVCC" in summary
    assert "Raft-Election" in summary
    assert "Shadow Evaluator Directives" in summary


def test_cognitive_graph_serialization_roundtrip():
    graph = CognitiveMemoryGraph()
    graph.record_finding(
        topic="React-Fiber",
        category="frontend",
        status=CompetencyStatus.VERIFIED,
        claim="Dual buffering tree mechanism",
        finding="Accurate architectural breakdown",
        turn_index=3,
        confidence=0.95,
    )
    graph.working_memory.current_topic = "React Reconciler"
    graph.working_memory.candidate_code = "function reconcile() {}"

    serialized = graph.to_dict()
    restored = CognitiveMemoryGraph.from_dict(serialized)

    assert "react-fiber" in restored.nodes
    node = restored.nodes["react-fiber"]
    assert node.status == CompetencyStatus.VERIFIED
    assert node.confidence == 0.95
    assert restored.working_memory.current_topic == "React Reconciler"
    assert restored.working_memory.candidate_code == "function reconcile() {}"
