"""Grounding check: a value survives only if its quote really is in the source.

This runs on every extractor's output, rule-based or LLM. For the rule-based
extractor it is a safety net; for the LLM it is the main defence against a
fluent but invented answer. A failed check turns the field into not_found
with the reason recorded, so the reviewer sees what was dropped and why.
"""
from __future__ import annotations

import re

from .normalize import ascii_digits
from .schema import Candidate


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", ascii_digits(text)).strip().lower()


def check(field: str, cand: Candidate, source_text: str) -> str | None:
    """Returns None if grounded, else a human-readable reason."""
    haystack = _squash(source_text)
    if not cand.evidence:
        return "No quote was given for this value."
    for ev in cand.evidence:
        if _squash(ev.quote) not in haystack:
            return f"Quote not found in the source text: '{ev.quote[:80]}'."
    if field == "benefit_amount" and cand.value is not None:
        digits = str(int(cand.value))
        quotes = " ".join(ascii_digits(e.quote).replace(",", "") for e in cand.evidence)
        if digits not in quotes:
            return f"Amount {cand.value} does not appear in its own quote."
    return None


def apply(results: dict, source_text: str) -> dict:
    out = {}
    for field, (cand, reason) in results.items():
        if cand is not None:
            problem = check(field, cand, source_text)
            if problem:
                out[field] = (None, f"Dropped by grounding check: {problem} (extractor proposed: {cand.value!r})")
                continue
        out[field] = (cand, reason)
    return out
