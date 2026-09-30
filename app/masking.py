"""
Standard masking algorithms applied to columns flagged as PII/CII during a copy.

These are named/documented so the UI can display exactly which algorithm will
run (or did run) against a given column — required for both PG2PG (user picks
per-column) and ADLS2ADLS (algorithm is applied automatically to any column
listed in `masking_columns` of the relevant .conf entry).
"""
import hashlib
import hmac
import os

_HMAC_SALT = os.environ.get("MASKING_HMAC_SALT", "change-me-in-production-salt")

MASKING_ALGORITHMS = {
    "sha256_hash": {
        "label": "SHA-256 Hash",
        "description": (
            "One-way irreversible hash of the value (HMAC-SHA256 with a server-side "
            "salt). Same input always yields the same output, so joins/grouping on "
            "the masked column still work, but the original value cannot be recovered."
        ),
    },
    "partial_mask": {
        "label": "Partial Mask",
        "description": (
            "Keeps the first and last 2 characters visible and replaces everything "
            "else with '*'. Useful for columns where a human still needs to eyeball "
            "roughly-correct-looking data (e.g. emails, phone numbers)."
        ),
    },
    "full_redact": {
        "label": "Full Redact",
        "description": "Replaces the entire value with a fixed literal ('***MASKED***').",
    },
    "tokenize": {
        "label": "Deterministic Tokenization",
        "description": (
            "Replaces the value with a short deterministic token (TOK_xxxxxxxx) "
            "derived from an HMAC of the value, preserving referential uniqueness "
            "across the copied dataset without exposing the source value."
        ),
    },
}

DEFAULT_PG_MASKING_ALGORITHM = "sha256_hash"
# Algorithm auto-applied to any column listed in an ADLS conf's masking_columns.
DEFAULT_ADLS_MASKING_ALGORITHM = "sha256_hash"


def mask_value(value: str, algorithm: str) -> str:
    if value is None:
        return value
    value = str(value)
    if algorithm == "sha256_hash":
        return hmac.new(_HMAC_SALT.encode(), value.encode(), hashlib.sha256).hexdigest()
    if algorithm == "partial_mask":
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + ("*" * (len(value) - 4)) + value[-2:]
    if algorithm == "full_redact":
        return "***MASKED***"
    if algorithm == "tokenize":
        digest = hmac.new(_HMAC_SALT.encode(), value.encode(), hashlib.sha256).hexdigest()
        return f"TOK_{digest[:12]}"
    raise ValueError(f"Unknown masking algorithm: {algorithm}")


def algorithm_choices():
    """Returns [(key, label), ...] for populating <select> options."""
    return [(key, meta["label"]) for key, meta in MASKING_ALGORITHMS.items()]
