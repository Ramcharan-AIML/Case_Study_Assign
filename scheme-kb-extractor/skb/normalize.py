"""Turning raw text into comparable values: amounts, frequencies, dates, benefit type.

Each function works on English, Hindi and Marathi text, because the same
scheme can be described in all three across different sources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def ascii_digits(text: str) -> str:
    return text.translate(_DEV_DIGITS)


# --- Amounts -----------------------------------------------------------------

_CURRENCY = r"(?:₹|Rs\.?|INR|रु\.?|रू\.?)"
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT_RE = re.compile(rf"{_CURRENCY}\s*({_NUMBER})|({_NUMBER})\s*(?:/-|rupees|रुपये|रुपए)", re.I)
# Words that mark an amount as historical ("revises the earlier Rs 1,000") or as
# an eligibility ceiling rather than the benefit itself.
_NOT_BENEFIT_CUES = re.compile(
    r"earlier|previous|previously|revises|instead of|पहले|पूर्व|पूर्वी|income|आय|उत्पन्न|not exceeding|से अधिक|पेक्षा",
    re.I,
)


@dataclass
class Amount:
    value: int
    start: int
    end: int
    skipped_reason: str | None = None


def find_amounts(text: str) -> list[Amount]:
    """All rupee amounts in the text; historical/ceiling amounts are flagged, not dropped."""
    t = ascii_digits(text)
    out = []
    for m in _AMOUNT_RE.finditer(t):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        try:
            val = int(float(raw))
        except ValueError:
            continue
        window = t[max(0, m.start() - 45) : m.start()]
        cue = _NOT_BENEFIT_CUES.search(window)
        out.append(Amount(val, m.start(), m.end(), f"preceded by '{cue.group(0)}'" if cue else None))
    return out


def benefit_amount(text: str) -> tuple[int | None, list[Amount]]:
    amounts = find_amounts(text)
    current = [a for a in amounts if not a.skipped_reason]
    return (current[0].value if current else None), amounts


VAGUE_AMOUNT_RE = re.compile(r"as per (?:the )?(?:prevailing )?norms[^.]*|as applicable|नियमानुसार|नियमांनुसार", re.I)

# --- Frequency ---------------------------------------------------------------

_FREQ_PATTERNS = [
    ("monthly", r"per month|monthly|a month|प्रति ?माह|मासिक|दरमहा|प्रतिमहिना"),
    ("annual", r"per year|per annum|annual(?:ly)? (?:assistance|grant|benefit)|yearly|प्रति ?वर्ष|सालाना|दरवर्षी"),
    ("one_time", r"one[- ]time|lump ?sum|एकमुश्त|एकरकमी|एक बार"),
    ("instalments", r"instal+ments?|किस्तों|हप्त्यां?त"),
]


def frequency(text: str) -> tuple[str | None, str | None]:
    """Returns (enum value, matched phrase)."""
    for label, pat in _FREQ_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            return label, m.group(0)
    return None, None


# --- Benefit type ------------------------------------------------------------

_CASH = r"\bDBT\b|bank account|financial assistance|pension|₹|Rs\.|बैंक खाते|बँक खात्यात|अर्थसहाय्य|राशि"
_IN_KIND = r"\bkit\b|ration|uniform|bicycle|किट|राशन|साइकिल"


def benefit_type(text: str) -> tuple[str | None, str | None]:
    cash = re.search(_CASH, text, re.I)
    kind = re.search(_IN_KIND, text, re.I)
    if cash and kind:
        return "cash + in-kind", f"{cash.group(0)} … {kind.group(0)}"
    if cash:
        return "cash", cash.group(0)
    if kind:
        return "in-kind", kind.group(0)
    return None, None


# --- Dates / deadlines -------------------------------------------------------

_MONTHS = {
    1: ["january", "jan", "जनवरी", "जानेवारी"],
    2: ["february", "feb", "फरवरी", "फ़रवरी", "फेब्रुवारी"],
    3: ["march", "mar", "मार्च"],
    4: ["april", "apr", "अप्रैल", "एप्रिल"],
    5: ["may", "मई", "मे"],
    6: ["june", "jun", "जून"],
    7: ["july", "jul", "जुलाई", "जुलै"],
    8: ["august", "aug", "अगस्त", "ऑगस्ट"],
    9: ["september", "sept", "sep", "सितंबर", "सितम्बर", "सप्टेंबर"],
    10: ["october", "oct", "अक्टूबर", "ऑक्टोबर"],
    11: ["november", "nov", "नवंबर", "नवम्बर", "नोव्हेंबर"],
    12: ["december", "dec", "दिसंबर", "दिसम्बर", "डिसेंबर"],
}
_MONTH_LOOKUP = {name: num for num, names in _MONTHS.items() for name in names}
_MONTH_ALT = "|".join(sorted(map(re.escape, _MONTH_LOOKUP), key=len, reverse=True))
_DATE_WORDS = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})", re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")

ROLLING_RE = re.compile(r"throughout the year|open all year|no last date|पूरे वर्ष|वर्षभर|कोई अंतिम तिथि नहीं", re.I)
RELATIVE_RE = re.compile(r"within (\d+) (days|months) (?:of|from) ([a-z ]+?)(?:[.,;]|$)", re.I)
ROLLING_VALUE = "No fixed deadline (open throughout the year)"


def find_dates(text: str) -> list[str]:
    """ISO dates in order of appearance. Works with Devanagari digits and month names."""
    t = ascii_digits(text)
    found: list[tuple[int, str]] = []
    for m in _DATE_WORDS.finditer(t):
        d, mon, y = int(m.group(1)), _MONTH_LOOKUP[m.group(2).lower()], int(m.group(3))
        found.append((m.start(), f"{y:04d}-{mon:02d}-{d:02d}"))
    for m in _DATE_NUM.finditer(t):
        d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mon <= 12 and 1 <= d <= 31:
            found.append((m.start(), f"{y:04d}-{mon:02d}-{d:02d}"))
    return [iso for _, iso in sorted(found)]


def relative_deadline(text: str) -> str | None:
    m = RELATIVE_RE.search(text)
    if not m:
        return None
    return f"Within {m.group(1)} {m.group(2)} of {m.group(3).strip()}"
