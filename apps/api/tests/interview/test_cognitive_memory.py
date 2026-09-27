"""Unit tests for CognitiveMemoryGraph and CompetencyNode."""

from realmock.domains.interview.agents.memory import (
    CognitiveMemoryGraph,
    CompetencyStatus,
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

    serialized = graph.to_dict()
    restored = CognitiveMemoryGraph.from_dict(serialized)

    assert "react-fiber" in restored.nodes
    node = restored.nodes["react-fiber"]
    assert node.status == CompetencyStatus.VERIFIED
    assert node.confidence == 0.95
    assert restored.working_memory.current_topic == "React Reconciler"


def test_cognitive_graph_corrupted_data_resilience():
    corrupted_data = {
        "nodes": {
            "invalid_node": {
                "topic": "CorruptedTopic",
                "status": "not_a_valid_status",
                "confidence": "invalid_conf_string",
                "evidence": [
                    {"turn_index": "not_int", "confidence": "bad", "claim": 123},
                    "corrupted_string_item",
                ],
            }
        },
        "working_memory": "not_a_dict",
    }
    restored = CognitiveMemoryGraph.from_dict(corrupted_data)
    assert "invalid_node" in restored.nodes
    node = restored.nodes["invalid_node"]
    assert node.status == CompetencyStatus.UNTESTED
    assert node.confidence == 0.0
    assert len(node.evidence) == 1
    assert node.evidence[0].turn_index == 0
    assert restored.working_memory.current_topic == ""


# ---- growth caps ----


def test_evidence_cap_keeps_latest_entries():
    from realmock.domains.interview.agents.memory.cognitive_graph import MAX_EVIDENCE_PER_NODE

    graph = CognitiveMemoryGraph()
    for i in range(MAX_EVIDENCE_PER_NODE + 4):
        graph.record_finding(
            topic="MySQL",
            status=CompetencyStatus.VERIFIED,
            claim=f"claim-{i}",
            finding=f"finding-{i}",
            turn_index=i,
        )
    node = graph.nodes["mysql"]
    assert len(node.evidence) == MAX_EVIDENCE_PER_NODE
    assert node.evidence[-1].claim == f"claim-{MAX_EVIDENCE_PER_NODE + 3}"


def test_node_cap_evicts_stalest():
    from realmock.domains.interview.agents.memory.cognitive_graph import MAX_NODES

    graph = CognitiveMemoryGraph()
    for i in range(MAX_NODES):
        graph.record_finding(
            topic=f"topic-{i}",
            status=CompetencyStatus.VERIFIED,
            claim="c",
            finding="f",
            turn_index=i,
        )
        graph.nodes[f"topic-{i}"].evidence[0].timestamp = float(i + 1)
    assert len(graph.nodes) == MAX_NODES

    # New node over the cap evicts the stalest (topic-0 has the oldest evidence).
    graph.record_finding(
        topic="topic-new",
        status=CompetencyStatus.SUSPICIOUS,
        claim="c",
        finding="f",
        turn_index=999,
    )
    assert len(graph.nodes) == MAX_NODES
    assert "topic-new" in graph.nodes
    assert "topic-0" not in graph.nodes
