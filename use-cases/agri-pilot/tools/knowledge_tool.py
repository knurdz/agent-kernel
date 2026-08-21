"""Agricultural knowledge RAG tool for AgriPilot (Increment 3.3).

Wraps a ChromaDB-backed `ChromaManager` (Increment 3.1, seeded by
`scripts/ingest_knowledge.py`, Increment 3.2) with a filtered retrieval
function. Filters by crop and, when known, disease and region, since a
treatment recommendation must be specific to the case (architecture doc
section 24). Below the relevance gate — no document matches the filters —
the tool reports no reliable evidence rather than falling back to a loose
semantic match, so the agent never invents a treatment (architecture doc
section 23, "RAG Failure").
"""

from __future__ import annotations

from typing import Any, Optional

from agentkernel.knowledgebase.chroma import ChromaManager

PERSIST_PATH = "data/chroma_db"
COLLECTION_NAME = "agri_knowledge"
NO_EVIDENCE_MESSAGE = (
    "I do not have enough verified information to give you a safe "
    "recommendation for this case."
)

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


def _build_where(crop: str, disease: Optional[str], region: Optional[str]) -> dict[str, Any]:
    """Build a Chroma `where` metadata filter from the known fields."""
    conditions: list[dict[str, Any]] = [{"crop": crop.strip().lower()}]
    if disease:
        conditions.append({"disease": disease.strip().lower()})
    if region:
        conditions.append({"region": region.strip().lower()})
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _query(
    manager: ChromaManager,
    crop: str,
    disease: Optional[str] = None,
    region: Optional[str] = None,
    growth_stage: Optional[str] = None,
) -> dict[str, Any]:
    """Filtered-retrieval core, separated out so tests can inject a manager."""
    where = _build_where(crop, disease, region)
    query_text = " ".join(part for part in [crop, disease, "treatment"] if part).strip()
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
            "region": meta.get("region"),
            "source": meta.get("source"),
        }
        for doc, meta in zip(documents, metadatas)
    ]
    return {"reliable": True, "evidence": evidence, "message": None}


def retrieve_treatment_info(
    crop: str,
    disease: Optional[str] = None,
    region: Optional[str] = None,
    growth_stage: Optional[str] = None,
) -> dict[str, Any]:
    """Retrieve verified treatment information for a diagnosed crop problem.

    Filters the knowledge base by crop and, if known, disease and region.
    Only call this with a crop, and a disease name if one has been
    diagnosed (e.g. by the vision specialist) — do not guess a disease
    name. If no verified document matches, `reliable` is False and you
    must relay `message` to the farmer instead of inventing a treatment.

    :param crop: Crop under discussion (e.g. "tomato").
    :param disease: Diagnosed disease name, if known (e.g. "early blight").
    :param region: Farmer's region, if known.
    :param growth_stage: Crop growth stage, if known (accepted for future
        filtering; not yet used to narrow results).
    :return: dict with "reliable" (bool), "evidence" (list of matched
        documents with crop/disease/region/source), and "message" (the
        safe-failure message when reliable is False, else None).
    """
    return _query(_get_manager(), crop, disease, region, growth_stage)
