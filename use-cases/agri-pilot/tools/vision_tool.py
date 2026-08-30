"""Vision tools for AgriPilot: image quality gate and disease classification.

See architecture doc section 20 ("Image Quality Cases") and section 21
("Vision Confidence"). The quality gate runs before classification so the
agent never wastes a model call, or a diagnosis, on an unusable photo.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
from PIL import Image

from tools.tool_guard import guarded

BLUR_VARIANCE_THRESHOLD = 100.0
DARKNESS_MEAN_THRESHOLD = 40.0
GREEN_PIXEL_RATIO_THRESHOLD = 0.08

# Pretrained crop-disease classifier (Increment 2.2). See README.md for the
# model choice and license note.
_MODEL_ID = "wambugu71/crop_leaf_diseases_vit"
_processor = None
_model = None


def _laplacian_variance(gray: np.ndarray) -> float:
    """Approximate a Laplacian sharpness score (no OpenCV dependency)."""
    padded = np.pad(gray, 1, mode="edge")
    conv = padded[:-2, 1:-1] + padded[1:-1, :-2] - 4 * padded[1:-1, 1:-1] + padded[1:-1, 2:] + padded[2:, 1:-1]
    return float(conv.var())


@guarded
def check_image_quality(image_path: str) -> dict[str, Any]:
    """Check whether a farmer-submitted crop image is usable for diagnosis.

    Call this before diagnose_crop_image. Detects a blurry image, a too-dark
    image, and a missing plant subject (architecture doc section 20).

    :param image_path: Path to the image file to check.
    :return: dict with "ok" (bool), "reason" (str, only set when not ok),
        and "metrics" (raw sharpness/brightness/green_ratio values).
    """
    # Increment 7.2 manual-testing hook: force the gate to fail so the
    # replanning flow is reachable from the text-only CLI.
    forced = os.environ.get("AGRIPILOT_DEBUG_IMAGE_QUALITY_FAIL", "").strip().lower()
    if forced:
        forced_reasons = {
            "blurry": "Image is too blurry to see leaf detail clearly.",
            "dark": "Image is too dark to see the affected area clearly.",
            "no_plant": "No plant leaves are clearly visible in this image.",
        }
        if forced in forced_reasons:
            return {"ok": False, "reason": forced_reasons[forced], "metrics": {}}
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - any load failure means poor quality
        return {"ok": False, "reason": f"Could not read the image file: {exc}", "metrics": {}}

    rgb = np.asarray(image, dtype=np.float32)
    gray = rgb.mean(axis=2)

    sharpness = _laplacian_variance(gray)
    brightness = float(gray.mean())

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    green_ratio = float(((g > r) & (g > b * 0.9)).mean())

    metrics = {"sharpness": sharpness, "brightness": brightness, "green_ratio": green_ratio}

    if brightness < DARKNESS_MEAN_THRESHOLD:
        return {"ok": False, "reason": "Image is too dark to see the affected area clearly.", "metrics": metrics}
    if sharpness < BLUR_VARIANCE_THRESHOLD:
        return {"ok": False, "reason": "Image is too blurry to see leaf detail clearly.", "metrics": metrics}
    if green_ratio < GREEN_PIXEL_RATIO_THRESHOLD:
        return {"ok": False, "reason": "No plant leaves are clearly visible in this image.", "metrics": metrics}

    return {"ok": True, "reason": None, "metrics": metrics}


def _load_model():
    """Load the classifier once and cache it at module scope."""
    global _processor, _model
    if _model is None:
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        _processor = AutoImageProcessor.from_pretrained(_MODEL_ID)
        _model = AutoModelForImageClassification.from_pretrained(_MODEL_ID)
        _model.eval()
    return _processor, _model


@guarded
def diagnose_crop_image(image_path: str) -> dict[str, Any]:
    """Classify a crop leaf image and return the top three disease predictions.

    Only call this after check_image_quality has reported ok=True. This
    returns raw model output only — do not treat the top label as a
    confirmed diagnosis; the calling agent applies a confidence threshold
    (architecture doc section 21, "Vision Confidence").

    :param image_path: Path to a quality-checked crop image.
    :return: {"predictions": [{"label": str, "confidence": float}, ...]},
        highest confidence first.
    """
    import torch

    processor, model = _load_model()
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    top = torch.topk(probs, k=min(3, probs.shape[-1]))

    predictions = [
        {"label": model.config.id2label[int(idx)], "confidence": round(float(prob), 4)}
        for prob, idx in zip(top.values, top.indices)
    ]
    return {"predictions": predictions}


CONFIDENCE_THRESHOLD = 0.7


def _short_advice_from_rag(crop: str, disease: str) -> str | None:
    """Pull a brief non-chemical snippet from the knowledge base when available."""
    try:
        from tools.knowledge_tool import _query, _get_manager

        result = _query(_get_manager(), crop, disease)
        if not result.get("reliable"):
            return None
        evidence = result.get("evidence") or []
        if not evidence:
            return None
        text = str(evidence[0].get("text") or "").strip()
        if not text:
            return None
        # First sentence only; avoid storing chemical/dosage detail on observations.
        for sep in (". ", "\n"):
            if sep in text:
                text = text.split(sep, 1)[0].strip()
                break
        return text[:280] if text else None
    except Exception:
        return None


def analyze_crop_photo(image_path: str, *, crop: str | None = None) -> dict[str, Any]:
    """Run quality gate + ViT classification for REST scan/tracking flows.

    Returns a structured dict suitable for API responses and DB persistence.
    Does not invoke the full LLM agent pipeline.
    """
    quality = check_image_quality(image_path)
    if not quality.get("ok"):
        return {
            "quality_ok": False,
            "quality_reason": quality.get("reason"),
            "metrics": quality.get("metrics"),
            "predictions": [],
            "top_label": None,
            "top_confidence": None,
            "confident": False,
            "advice_summary": None,
        }

    diagnosis = diagnose_crop_image(image_path)
    predictions = diagnosis.get("predictions") or []
    top = predictions[0] if predictions else None
    top_label = top["label"] if top else None
    top_confidence = top["confidence"] if top else None
    confident = top_confidence is not None and float(top_confidence) >= CONFIDENCE_THRESHOLD

    advice_summary = None
    if confident and top_label and crop:
        advice_summary = _short_advice_from_rag(crop.strip().lower(), top_label)

    return {
        "quality_ok": True,
        "quality_reason": None,
        "metrics": quality.get("metrics"),
        "predictions": predictions,
        "top_label": top_label,
        "top_confidence": top_confidence,
        "confident": confident,
        "advice_summary": advice_summary,
    }
