"""Reglas de campaña: esquema compartido (`docs/architecture.md §6.4`) y validación."""

from winclip.rules.schema import CampaignRules, RuleViolation, load_rules
from winclip.rules.validator import build_candidate_text, validate_candidate_text

__all__ = [
    "CampaignRules",
    "RuleViolation",
    "build_candidate_text",
    "load_rules",
    "validate_candidate_text",
]
