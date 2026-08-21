"""Deterministic safety validation tool for AgriPilot (Increment 4.1).

Checks a candidate chemical treatment recommendation against a fixed
allow-list of chemicals, safe dosage ranges, and known unsafe combinations
(`data/safety_rules.json`). This is a deterministic, rule-based check --
never an LLM judgment call -- so a hallucinated chemical name or dosage can
never reach the farmer un-vetted (architecture doc, "Safety and Treatment
Validation").

Verdicts:
- "allow": chemical is on the allow-list, dosage is within its safe
  range, and no unsafe combination applies.
- "reject": chemical and dosage are both known, but the dosage is
  outside the safe range, or the combination with another chemical is
  listed as unsafe.
- "escalate": the chemical is not on the allow-list, or the dosage unit
  cannot be compared against the rule -- needs a human to review.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

RULES_PATH = "data/safety_rules.json"


@lru_cache(maxsize=8)
def _load_rules(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_chemical(rules: dict[str, Any], chemical: str) -> Optional[str]:
    """Return the canonical chemical name, resolving aliases, or None."""
    name = chemical.strip().lower()
    chemicals = rules.get("chemicals", {})
    if name in chemicals:
        return name
    for canonical, info in chemicals.items():
        aliases = [a.strip().lower() for a in info.get("aliases", [])]
        if name in aliases:
            return canonical
    return None


def _check_combination(rules: dict[str, Any], canonical: str, combined_with: list[str]) -> Optional[str]:
    """Return an unsafe-combination reason if any partner chemical conflicts."""
    combined_lower = {c.strip().lower() for c in combined_with}
    for combo in rules.get("unsafe_combinations", []):
        pair = {c.strip().lower() for c in combo.get("chemicals", [])}
        if len(pair) == 2 and canonical in pair:
            other = (pair - {canonical}).pop()
            if other in combined_lower:
                return combo.get("reason", "This combination is not verified as safe.")
    return None


def _validate(
    rules_path: str,
    chemical: str,
    dosage: float,
    unit: str,
    combined_with: Optional[list[str]] = None,
) -> dict[str, str]:
    """Core validation logic, separated out so tests can inject a rules file."""
    rules = _load_rules(rules_path)
    canonical = _resolve_chemical(rules, chemical)

    if canonical is None:
        return {
            "verdict": "escalate",
            "reason": (
                f"'{chemical}' is not in the verified allow-list. Escalate to an "
                "agricultural officer before recommending it."
            ),
        }

    rule = rules["chemicals"][canonical]
    dosage_rule = rule["dosage"]

    if unit.strip().lower() != dosage_rule["unit"].strip().lower():
        return {
            "verdict": "escalate",
            "reason": (
                f"Dosage unit '{unit}' does not match the verified unit "
                f"'{dosage_rule['unit']}' for {canonical}; cannot safely compare. "
                "Escalate for manual review."
            ),
        }

    if not (dosage_rule["min"] <= dosage <= dosage_rule["max"]):
        return {
            "verdict": "reject",
            "reason": (
                f"{dosage} {unit} is outside the safe range "
                f"({dosage_rule['min']}-{dosage_rule['max']} {dosage_rule['unit']}) for {canonical}."
            ),
        }

    if combined_with:
        combo_reason = _check_combination(rules, canonical, combined_with)
        if combo_reason:
            return {"verdict": "reject", "reason": combo_reason}

    return {
        "verdict": "allow",
        "reason": f"{canonical} at {dosage} {unit} is within the verified safe range.",
    }


def resolve_chemical(chemical: str) -> Optional[str]:
    """Return the canonical name for a chemical or alias, or None if unknown.

    :param chemical: Chemical or product name as written (any case).
    :return: The canonical allow-list name, or None when not on the list.
    """
    return _resolve_chemical(_load_rules(RULES_PATH), chemical)


def known_chemical_names() -> set[str]:
    """Return every chemical name the rules recognize (canonical + aliases).

    Used by the knowledge-agent guardrail to detect replies that state a
    chemical treatment; all names are lowercased.
    """
    rules = _load_rules(RULES_PATH)
    names: set[str] = set()
    for canonical, info in rules.get("chemicals", {}).items():
        names.add(canonical.strip().lower())
        names.update(alias.strip().lower() for alias in info.get("aliases", []))
    return names


def known_dosage_units() -> set[str]:
    """Return every dosage unit used by the rules (e.g. {"g/L"}), lowercased.

    Used by the knowledge-agent guardrail to detect dosage figures in
    replies.
    """
    rules = _load_rules(RULES_PATH)
    units: set[str] = set()
    for info in rules.get("chemicals", {}).values():
        unit = info.get("dosage", {}).get("unit")
        if unit:
            units.add(unit.strip().lower())
    return units


def validate_treatment(
    chemical: str,
    dosage: float,
    unit: str,
    combined_with: Optional[list[str]] = None,
) -> dict[str, str]:
    """Validate a candidate chemical treatment recommendation before it is
    relayed to a farmer.

    This is a deterministic check against a fixed allow-list -- it never
    infers a chemical's safety from an LLM. Always call this before
    including any chemical name and dosage in a reply. Never alter the
    verdict or its reasoning.

    :param chemical: Chemical or product name (e.g. "copper hydroxide").
        Common aliases (e.g. "copper-based fungicide") are recognized.
    :param dosage: Numeric dosage amount.
    :param unit: Unit for the dosage (e.g. "g/L"). Must match the unit
        used in the verified rule or the case is escalated.
    :param combined_with: Other chemical names being applied in the same
        treatment, if any, so unsafe combinations can be checked.
    :return: dict with "verdict" ("allow", "reject", or "escalate") and
        "reason" (a plain-language explanation).
    """
    return _validate(RULES_PATH, chemical, dosage, unit, combined_with)
