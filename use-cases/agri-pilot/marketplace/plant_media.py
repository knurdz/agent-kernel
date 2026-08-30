"""On-disk storage for plant observation photos."""

from __future__ import annotations

import os
import pathlib
import uuid
from typing import BinaryIO

DEFAULT_MEDIA_ROOT = "data/plant_media"


def media_root() -> pathlib.Path:
    root = os.environ.get("AGRIPILOT_PLANT_MEDIA_ROOT", DEFAULT_MEDIA_ROOT)
    path = pathlib.Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_plant_photo(farmer_id: int, plant_id: int, file_obj: BinaryIO, filename: str) -> str:
    """Persist an uploaded photo and return a relative path stored in the DB."""
    ext = pathlib.Path(filename).suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    rel_dir = pathlib.Path(str(farmer_id)) / str(plant_id)
    dest_dir = media_root() / rel_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    rel_path = rel_dir / name
    dest = media_root() / rel_path
    with open(dest, "wb") as out:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return str(rel_path).replace("\\", "/")


def resolve_photo_path(relative_path: str) -> pathlib.Path:
    """Resolve a DB-stored relative path to an absolute filesystem path."""
    root = media_root().resolve()
    candidate = (root / relative_path).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError("invalid photo path")
    return candidate
