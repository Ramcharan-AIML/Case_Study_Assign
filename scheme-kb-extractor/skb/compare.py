"""When do two values for the same field mean the same thing?

Used twice: by the reconciler (do two sources agree?) and by the evaluator
(does the extraction match the hand-checked answer?). Keeping one definition
means "conflict" and "correct" can never drift apart.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .normalize import ascii_digits
from .schema import LIST_FIELDS

# Canonical document codes so "आधार कार्ड" and "Aadhaar card" count as the same
# document. In production this would be Haqdarshak's own document master list.
DOC_CANON = {
    "aadhaar": ["aadhaar", "aadhar", "आधार"],
    "income_certificate": ["income certificate", "आय प्रमाण", "उत्पन्नाचा दाखला", "उत्पन्न प्रमाणपत्र"],
    "bank_passbook": ["bank passbook", "passbook", "बैंक पासबुक", "बँक पासबुक"],
    "domicile_certificate": ["domicile", "मूल निवास", "अधिवास", "रहिवासी दाखला"],
    "age_proof": ["age proof", "birth certificate", "आयु प्रमाण", "वयाचा दाखला"],
    "death_certificate_spouse": ["death certificate", "मृत्यू दाखला", "मृत्यु प्रमाण"],
    "mcp_card": ["mcp card", "mother and child protection"],
    "school_admission_certificate": ["admission certificate", "प्रवेश प्रमाण"],
}


def norm_text(s: Any) -> str:
    s = ascii_digits(str(s)).lower()
    s = re.sub(r"[\s‌‍]+", " ", s)
    return s.strip(" .।,;:-")


def doc_code(item: str) -> str | None:
    t = norm_text(item)
    for code, names in DOC_CANON.items():
        if any(n in t for n in names):
            return code
    return None


def text_similar(a: Any, b: Any, threshold: float = 0.85) -> bool:
    x, y = norm_text(a), norm_text(b)
    if not x or not y:
        return False
    if x == y or (min(len(x), len(y)) >= 12 and (x in y or y in x)):
        return True
    return SequenceMatcher(None, x, y).ratio() >= threshold


def _item_key(field: str, item: str) -> str:
    if field == "documents_required":
        return doc_code(item) or norm_text(item)
    return norm_text(item)


def list_match(field: str, a: list, b: list) -> tuple[float, float]:
    """(precision, recall) of list a against list b, with fuzzy item matching."""
    if not a or not b:
        return 0.0, 0.0
    unmatched = list(b)
    hits = 0
    for item in a:
        for other in unmatched:
            ka, kb = _item_key(field, item), _item_key(field, other)
            if ka == kb or text_similar(item, other, 0.8):
                unmatched.remove(other)
                hits += 1
                break
    return hits / len(a), hits / len(b)


def values_equal(field: str, a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if field in LIST_FIELDS:
        a, b = list(a), list(b)
        p, r = list_match(field, a, b)
        if field == "documents_required":
            # A missing document gets an application rejected, so lists must match exactly.
            return p == 1.0 and r == 1.0
        f1 = 0 if p + r == 0 else 2 * p * r / (p + r)
        return f1 >= 0.8
    if field == "benefit_amount":
        try:
            return int(a) == int(b)
        except (TypeError, ValueError):
            return False
    if field in {"benefit_frequency", "benefit_type", "deadline", "official_link"}:
        return norm_text(a) == norm_text(b)
    return text_similar(a, b)
