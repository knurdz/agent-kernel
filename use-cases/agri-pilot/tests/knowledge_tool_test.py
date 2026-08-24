"""Unit tests for tools/knowledge_tool.py (Increments 3.1, 3.3).

Uses a throwaway ChromaManager persisted under tmp_path so tests are
isolated from the real seeded knowledge base and from each other.
"""

import pytest
from agentkernel.knowledgebase.chroma import ChromaManager

from tools.knowledge_tool import _query


@pytest.fixture()
def manager(tmp_path):
    m = ChromaManager(persist_path=str(tmp_path / "chroma_db"), collection_name="test_kb")
    m.write(
        [
            {
                "text": "Remove infected leaves and apply a copper fungicide per label.",
                "metadata": {"crop": "tomato", "disease": "early blight", "region": "general"},
            }
        ]
    )
    return m


def test_write_and_read_round_trip(manager):
    """Increment 3.1: write one document, read it back through the backend."""
    results = manager.read("early blight tomato", limit=3)
    assert len(results) == 1
    assert "copper fungicide" in results[0]["text"]
    assert results[0]["metadata"]["disease"] == "early blight"


def test_known_crop_and_disease_returns_document(manager):
    """Increment 3.3: known crop+disease returns the seeded document."""
    result = _query(manager, crop="tomato", disease="early blight")
    assert result["reliable"] is True
    assert len(result["evidence"]) == 1
    assert "copper fungicide" in result["evidence"][0]["text"]


def test_nonsense_disease_returns_no_reliable_evidence(manager):
    """Increment 3.3: an unseeded disease name returns the safe-failure path."""
    result = _query(manager, crop="tomato", disease="glorbnitis")
    assert result["reliable"] is False
    assert result["evidence"] == []
    assert "do not have enough verified information" in result["message"]


def test_unknown_crop_returns_no_reliable_evidence(manager):
    result = _query(manager, crop="durian")
    assert result["reliable"] is False
