"""Agricultural knowledge RAG tool for AgriPilot (Increment 3.3).

Wraps a ChromaDB-backed `ChromaManager` (Increment 3.1, seeded by
`scripts/ingest_knowledge.py`, Increment 3.2) with a filtered retrieval
function. Filters by crop and, when known, disease, since a treatment
recommendation must be specific to the case (architecture doc section 24).
Below the relevance gate — no document matches the filters —
the tool reports no reliable evidence rather than falling back to a loose
semantic match, so the agent never invents a treatment (architecture doc
section 23, "RAG Failure").
"""

from __future__ import annotations

from typing import Any, Optional

from agentkernel.knowledgebase.chroma import ChromaManager

from tools.tool_guard import guarded

PERSIST_PATH = "data/chroma_db"
COLLECTION_NAME = "agri_knowledge"
NO_EVIDENCE_MESSAGE = "I do not have enough verified information to give you a safe " "recommendation for this case."

_manager: Optional[ChromaManager] = None


def _get_manager() -> ChromaManager:
    """Return the module-level `ChromaManager`, connecting on first use."""
    global _manager
    if _manager is None:
        _manager = ChromaManager(
            persist_path=PERSIST_PATH,
            name="agri_kb",
            collection_name=COLLECTION_NAME,
            description="Verified agricultural crop/disease/treatment knowledge",
        )
    return _manager


def _build_where(
    crop: str,
    disease: Optional[str] = None,
    topic: Optional[str] = None,
) -> dict[str, Any]:
    """Build a Chroma `where` metadata filter from the known fields."""
    conditions: list[dict[str, Any]] = [{"crop": crop.strip().lower()}]
    if disease:
        conditions.append({"disease": disease.strip().lower()})
    elif topic:
        conditions.append({"topic": topic.strip().lower()})
    else:
        conditions.append({"topic": "disease"})
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _query(
    manager: ChromaManager,
    crop: str,
    disease: Optional[str] = None,
    growth_stage: Optional[str] = None,
    topic: Optional[str] = None,
) -> dict[str, Any]:
    """Filtered-retrieval core, separated out so tests can inject a manager."""
    effective_topic = topic
    if disease:
        effective_topic = None
    elif not effective_topic:
        effective_topic = "disease"
    where = _build_where(crop, disease, effective_topic if not disease else None)
    query_parts = [crop]
    if disease:
        query_parts.extend([disease, "treatment"])
    elif effective_topic:
        query_parts.append(effective_topic)
    query_text = " ".join(query_parts).strip()
    results = manager.collection.query(query_texts=[query_text], n_results=3, where=where)

    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]

    if not documents:
        return {"reliable": False, "evidence": [], "message": NO_EVIDENCE_MESSAGE}

    evidence = [
        {
            "text": doc,
            "crop": meta.get("crop"),
            "disease": meta.get("disease"),
            "topic": meta.get("topic"),
            "source": meta.get("source"),
        }
        for doc, meta in zip(documents, metadatas)
    ]
    return {"reliable": True, "evidence": evidence, "message": None}


@guarded
def retrieve_treatment_info(
    crop: str,
    disease: Optional[str] = None,
    growth_stage: Optional[str] = None,
    topic: Optional[str] = None,
) -> dict[str, Any]:
    """Retrieve verified agricultural information for a crop problem or crop-care question.

    Filters the knowledge base by crop and, when relevant, disease or topic.
    For treatment, pass crop + disease (do not guess a disease name).
    For growing, nutrients, or harvest questions, pass crop + topic
    (cultivation, nutrients, or harvest) and leave disease empty.
    If only crop is given, defaults to disease/treatment docs.
    If no verified document matches, `reliable` is False — relay `message`
    instead of inventing advice.

    :param crop: Crop under discussion (e.g. "tomato").
    :param disease: Diagnosed disease name, if known (e.g. "early blight").
    :param growth_stage: Crop growth stage, if known (accepted for future
        filtering; not yet used to narrow results).
    :param topic: cultivation, nutrients, or harvest for non-disease questions.
    :return: dict with "reliable" (bool), "evidence" (list of matched
        documents with crop/disease/topic/source), and "message".
    """
    return _query(_get_manager(), crop, disease, growth_stage, topic)
