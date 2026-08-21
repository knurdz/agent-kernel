"""Unit tests for tools/safety_tool.py (Increment 4.1).

Uses a throwaway rules file written under tmp_path so tests are isolated
from the real `data/safety_rules.json` and from each other.
"""

import json

import pytest

from tools.safety_tool import _validate

RULES = {
    "chemicals": {
        "copper hydroxide": {
            "aliases": ["copper-based fungicide", "copper fungicide"],
            "dosage": {"min": 2.0, "max": 4.0, "unit": "g/L"},
        },
        "chlorothalonil": {
            "aliases": [],
            "dosage": {"min": 1.5, "max": 2.5, "unit": "g/L"},
        },
        "mancozeb": {
            "aliases": [],
            "dosage": {"min": 2.0, "max": 3.0, "unit": "g/L"},
        },
    },
    "unsafe_combinations": [
        {
            "chemicals": ["chlorothalonil", "mancozeb"],
            "reason": "Tank-mixing is not covered by either product label.",
        }
    ],
}


@pytest.fixture()
def rules_path(tmp_path):
    path = tmp_path / "safety_rules.json"
    path.write_text(json.dumps(RULES))
    return str(path)


def test_safe_dosage_within_range_is_allowed(rules_path):
    result = _validate(rules_path, chemical="copper hydroxide", dosage=3.0, unit="g/L")
    assert result["verdict"] == "allow"
    assert result["reason"]


def test_dosage_above_range_is_rejected(rules_path):
    result = _validate(rules_path, chemical="copper hydroxide", dosage=10.0, unit="g/L")
    assert result["verdict"] == "reject"
    assert "range" in result["reason"].lower()


def test_dosage_below_range_is_rejected(rules_path):
    result = _validate(rules_path, chemical="copper hydroxide", dosage=0.5, unit="g/L")
    assert result["verdict"] == "reject"


def test_unknown_chemical_is_escalated(rules_path):
    result = _validate(rules_path, chemical="glorbicide-9000", dosage=1.0, unit="g/L")
    assert result["verdict"] == "escalate"
    assert "not in" in result["reason"].lower() or "allow-list" in result["reason"].lower()


def test_alias_resolves_to_canonical_chemical(rules_path):
    result = _validate(rules_path, chemical="copper-based fungicide", dosage=3.0, unit="g/L")
    assert result["verdict"] == "allow"


def test_unit_mismatch_is_escalated(rules_path):
    result = _validate(rules_path, chemical="copper hydroxide", dosage=3.0, unit="oz/gal")
    assert result["verdict"] == "escalate"


def test_unsafe_combination_is_rejected(rules_path):
    result = _validate(
        rules_path,
        chemical="chlorothalonil",
        dosage=2.0,
        unit="g/L",
        combined_with=["mancozeb"],
    )
    assert result["verdict"] == "reject"
    assert "tank-mix" in result["reason"].lower() or "mancozeb" in result["reason"].lower()


def test_safe_combination_is_allowed(rules_path):
    result = _validate(
        rules_path,
        chemical="copper hydroxide",
        dosage=3.0,
        unit="g/L",
        combined_with=["chlorothalonil"],
    )
    assert result["verdict"] == "allow"
