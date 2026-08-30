"""Ingest verified knowledge documents from data/knowledge_docs/ into ChromaDB.

Increment 3.2. Each source file is a small header of `key: value` lines
(crop, disease, source), a `===` separator, then the document body.
One Chroma record is written per source file (no chunking) so the ingested
record count can be checked directly against the number of source files.

Run with: uv run python scripts/ingest_knowledge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentkernel.knowledgebase.chroma import ChromaManager

from tools.crop_guide import GUIDES_DIR, guide_to_chroma_records, load_crop_guide

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_docs"
PERSIST_PATH = str(Path(__file__).resolve().parent.parent / "data" / "chroma_db")
COLLECTION_NAME = "agri_knowledge"
HEADER_SEPARATOR = "===\n"


def parse_doc(path: Path) -> dict:
    """Parse one knowledge doc file into a Chroma record.

    :param path: Path to a `key: value` header + `===` + body source file.
    :return: Record dict with `text` (the body) and `metadata` (header
        fields, lowercased, plus the source filename).
    """
    raw = path.read_text(encoding="utf-8")
    header_text, _, body = raw.partition(HEADER_SEPARATOR)
    metadata: dict = {"filename": path.name}
    for line in header_text.strip().splitlines():
        key, _, value = line.partition(":")
        if key.strip():
            metadata[key.strip().lower()] = value.strip().lower()
    if "topic" not in metadata and metadata.get("disease"):
        metadata["topic"] = "disease"
    return {"text": body.strip(), "metadata": metadata}


def main() -> None:
    files = sorted(DOCS_DIR.glob("*.md"))
    records = [parse_doc(f) for f in files]

    guide_files = sorted(GUIDES_DIR.glob("*.json")) if GUIDES_DIR.is_dir() else []
    for path in guide_files:
        guide = load_crop_guide(path.stem)
        if guide:
            records.extend(guide_to_chroma_records(guide))

    if not records:
        print(f"No documents found in {DOCS_DIR} or {GUIDES_DIR}")
        return
    manager = ChromaManager(
        persist_path=PERSIST_PATH,
        name="agri_kb",
        collection_name=COLLECTION_NAME,
        description="Verified agricultural crop/disease/treatment knowledge",
    )
    manager.write(records)

    count = manager.collection.count()
    print(f"Ingested {len(records)} source file(s) from {DOCS_DIR}")
    print(f"Collection '{COLLECTION_NAME}' now has {count} record(s) at {PERSIST_PATH}")


if __name__ == "__main__":
    main()
