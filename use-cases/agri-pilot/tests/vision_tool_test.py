"""Unit tests for tools/vision_tool.py (Increments 2.1-2.2).

Sample images are generated in-memory (no binary test fixtures needed) so
these tests are deterministic and don't depend on external photos.
"""

import numpy as np
import pytest
from PIL import Image, ImageFilter

from tools.vision_tool import check_image_quality


def _save(tmp_path, name: str, array: np.ndarray) -> str:
    path = tmp_path / name
    Image.fromarray(array.astype("uint8"), mode="RGB").save(path)
    return str(path)


def _clear_leaf_image() -> np.ndarray:
    """A bright, sharp, mostly-green image with a checkerboard for edges."""
    arr = np.zeros((224, 224, 3), dtype=np.uint8)
    arr[..., 1] = 160  # green channel
    arr[::8, :, :] = 40  # sharp edges every 8 rows
    arr[:, ::8, :] = 40
    return arr


def test_clear_image_passes(tmp_path):
    path = _save(tmp_path, "clear.png", _clear_leaf_image())
    result = check_image_quality(path)
    assert result["ok"] is True
    assert result["reason"] is None


def test_blurry_image_rejected(tmp_path):
    sharp = Image.fromarray(_clear_leaf_image().astype("uint8"), mode="RGB")
    blurry = sharp.filter(ImageFilter.GaussianBlur(radius=12))
    path = tmp_path / "blurry.png"
    blurry.save(path)

    result = check_image_quality(str(path))
    assert result["ok"] is False
    assert "blurry" in result["reason"].lower()


def test_dark_image_rejected(tmp_path):
    arr = np.full((224, 224, 3), 5, dtype=np.uint8)
    path = _save(tmp_path, "dark.png", arr)
    result = check_image_quality(path)
    assert result["ok"] is False
    assert "dark" in result["reason"].lower()


def test_missing_file_rejected(tmp_path):
    result = check_image_quality(str(tmp_path / "does_not_exist.png"))
    assert result["ok"] is False
    assert result["reason"] is not None


@pytest.mark.slow
def test_diagnose_crop_image_returns_valid_predictions(tmp_path):
    """Increment 2.2. Downloads model weights on first run; marked slow."""
    from tools.vision_tool import diagnose_crop_image

    path = _save(tmp_path, "leaf.png", _clear_leaf_image())
    result = diagnose_crop_image(path)

    predictions = result["predictions"]
    assert 1 <= len(predictions) <= 3
    for pred in predictions:
        assert isinstance(pred["label"], str) and pred["label"]
        assert 0.0 <= pred["confidence"] <= 1.0
    # Highest confidence first.
    confidences = [p["confidence"] for p in predictions]
    assert confidences == sorted(confidences, reverse=True)
