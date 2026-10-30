"""Offline, rule-based extractor (no API key needed).

Purpose: a deterministic baseline so the whole pipeline (evidence, conflicts,
review, evaluation) runs anywhere. It relies on documents having labelled
sections ("Benefit:", "लाभ", "पात्रता:" ...), which most notifications do.
It cannot read scanned images: for those it says so and returns nothing,
rather than guessing. The LLM extractor (extract_llm.py) is the real one.
"""
from __future__ import annotations

import re

from . import normalize as nz
from .loaders import Document, Line
from .schema import FIELDS, Candidate, Evidence

ALIASES = {
    "scheme_name": ["scheme name", "name of the scheme", "योजना का नाम", "योजनेचे नाव"],
    "department": ["department", "विभाग"],
    "benefit": ["benefit", "benefits", "assistance", "लाभ", "लाभ राशि"],
    "eligibility": ["eligibility", "eligibility criteria", "who can apply", "पात्रता"],
    "documents_required": ["documents required", "required documents", "documents", "आवश्यक दस्तावेज़",
                           "आवश्यक दस्तावेज", "दस्तावेज़", "आवश्यक कागदपत्रे", "कागदपत्रे"],
    "how_to_apply": ["how to apply", "application process", "आवेदन कैसे करें", "आवेदन प्रक्रिया", "अर्ज कसा करावा"],
    "deadline": ["last date", "deadline", "last date to apply", "अंतिम तिथि", "अंतिम दिनांक", "अंतिम तारीख"],
    "official_link": ["official link", "official website", "website", "वेबसाइट"],
}
_ALIAS_TO_SECTION = {a: s for s, names in ALIASES.items() for a in names}
_LABEL_RE = re.compile(r"^\s*(?:(?:[0-9०-९]+|[a-z])[.)])?\s*([^:：]{2,40}?)\s*[:：]\s*(.*)$", re.I)
_MARKER_RE = re.compile(r"^\s*(?:[0-9०-९]{1,2}[.)]|[a-z][.)]|\([a-z0-9]\)|[•\-–*])\s+", re.I)
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")
_NAME_RE = re.compile(r"\b((?:[A-Z][a-z]+ ){1,5}Yojana)\b")
_DEPT_RE = re.compile(r"\b(Department of [A-Z][A-Za-z&]*(?: (?:and|of|&|[A-Z][A-Za-z&]*))*)")
_DEADLINE_CUE = re.compile(r"last date|must be (?:made|submitted)|apply by|within \d+ (?:days|months)", re.I)

SectionLines = dict[str, list[tuple[Line, str]]]  # section -> [(line, content text)]


def sectionize(doc: Document) -> SectionLines:
    sections: SectionLines = {}
    current: str | None = None
    for line in doc.lines:
        if line.section_hint:  # structured source: section is known
            sections.setdefault(line.section_hint, []).append((line, line.text))
            continue
        if line.tag == "h1":
            sections.setdefault("title", []).append((line, line.text))
            current = None
            continue
        if line.tag in ("h2", "h3"):
            current = _ALIAS_TO_SECTION.get(_label(line.text))
            continue
        m = _LABEL_RE.match(line.text)
        if m and _label(m.group(1)) in _ALIAS_TO_SECTION:
            current = _ALIAS_TO_SECTION[_label(m.group(1))]
            if m.group(2).strip():
                sections.setdefault(current, []).append((line, m.group(2).strip()))
            continue
        if m and not _MARKER_RE.match(line.text) and len(m.group(1)) < 25:
            current = None  # an unrelated label such as "Subject:" or "Date:" ends the section
            continue
        if line.tag == "para":
            current = None  # new paragraph in a plain-text note
            continue
        if current:
            sections.setdefault(current, []).append((line, line.text))
    return sections


def _label(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _ev(doc: Document, line: Line, quote: str | None = None) -> Evidence:
    s = doc.source
    return Evidence(quote=quote or line.text, location=line.location, source_ref=s.source_ref,
                    source_link=s.link, captured_at=s.captured_at)


def _cand(doc: Document, value, evidence: list[Evidence], conf: float, note: str | None = None) -> Candidate:
    return Candidate(value=value, evidence=evidence, confidence=conf, source_ref=doc.source.source_ref,
                     authority=doc.source.authority, note=note)


Result = dict[str, tuple[Candidate | None, str | None]]  # field -> (candidate, reason if None)


def extract(doc: Document) -> Result:
    if doc.needs_ocr:
        reason = ("Source is a scanned image with no text layer. The offline extractor has no OCR, so it "
                  "returns nothing instead of guessing. Run with --mode llm (vision) or send to a researcher.")
        return {f: (None, reason) for f in FIELDS}

    sec = sectionize(doc)
    out: Result = {}
    out["scheme_name"] = _scheme_name(doc, sec)
    out["department"] = _department(doc, sec)
    out.update(_benefit(doc, sec))
    for f in ("eligibility", "documents_required", "how_to_apply"):
        out[f] = _list_field(doc, sec, f)
    out["deadline"] = _deadline(doc, sec)
    out["official_link"] = _official_link(doc, sec)
    return out


def _scheme_name(doc, sec):
    if sec.get("scheme_name"):
        line, text = sec["scheme_name"][0]
        return _cand(doc, text, [_ev(doc, line, text)], 0.9), None
    if sec.get("title"):
        line, text = sec["title"][0]
        return _cand(doc, text, [_ev(doc, line)], 0.8, "Taken from the page's main heading."), None
    for line in doc.lines[:15]:
        m = _NAME_RE.search(line.text)
        if m:
            return _cand(doc, m.group(1), [_ev(doc, line, m.group(1))], 0.6,
                         "No 'Scheme name' label; inferred from the headline."), None
    return None, "No scheme name label, heading or '... Yojana' phrase found."


def _department(doc, sec):
    if sec.get("department"):
        line, text = sec["department"][0]
        return _cand(doc, text, [_ev(doc, line, text)], 0.9), None
    for line in doc.lines[:10]:
        m = _DEPT_RE.search(line.text)
        if m:
            return _cand(doc, m.group(1), [_ev(doc, line, m.group(1))], 0.8), None
    return None, "No department named in the document header."


def _benefit(doc, sec) -> Result:
    lines = sec.get("benefit", [])
    if not lines:
        reason = "No 'Benefit' section found."
        return {f: (None, reason) for f in ("benefit_type", "benefit_amount", "benefit_frequency")}
    out: Result = {}
    joined = " ".join(t for _, t in lines)

    # Amount: first amount that is not marked historical / an income ceiling.
    amount_line, amount, skipped = None, None, []
    for line, text in lines:
        val, all_amounts = nz.benefit_amount(text)
        skipped += [f"Rs {a.value} ({a.skipped_reason})" for a in all_amounts if a.skipped_reason]
        if val is not None and amount is None:
            amount, amount_line = val, line
    if amount is not None:
        note = f"Ignored other amounts: {', '.join(skipped)}." if skipped else None
        out["benefit_amount"] = (_cand(doc, amount, [_ev(doc, amount_line)], 0.9, note), None)
    else:
        vague = nz.VAGUE_AMOUNT_RE.search(joined)
        out["benefit_amount"] = (None, f"Document gives no figure; it says '{vague.group(0).strip()}'." if vague
                                 else "No rupee amount in the benefit section.")

    # Frequency: prefer the line the amount came from.
    ordered = sorted(lines, key=lambda lt: lt[0] is not amount_line)
    for line, text in ordered:
        freq, phrase = nz.frequency(text)
        if freq:
            out["benefit_frequency"] = (_cand(doc, freq, [_ev(doc, line)], 0.85, f"Matched '{phrase}'."), None)
            break
    else:
        out["benefit_frequency"] = (None, "No frequency wording (monthly / annual / one-time) in the benefit section.")

    btype, phrase = nz.benefit_type(joined)
    if btype:
        ev_lines = []  # only the line(s) holding the wording that decided the type
        for part in phrase.split(" … "):
            hit = next((l for l, t in lines if part in t), None)
            if hit and hit not in ev_lines:
                ev_lines.append(hit)
        out["benefit_type"] = (_cand(doc, btype, [_ev(doc, l) for l in ev_lines], 0.75,
                                     f"Classified from wording: '{phrase}'."), None)
    else:
        out["benefit_type"] = (None, "Benefit wording does not say whether it is cash or in-kind.")
    return out


def _list_field(doc, sec, field):
    lines = sec.get(field, [])
    if not lines:
        return None, f"No '{field.replace('_', ' ')}' section found."
    items: list[str] = []
    evidence: list[Evidence] = []
    for line, text in lines:
        is_item = bool(_MARKER_RE.match(text)) or line.tag == "li"
        clean = _MARKER_RE.sub("", text).strip()
        if items and not is_item and line.tag != "li" and doc.source.kind == "pdf":
            items[-1] = f"{items[-1]} {clean}"  # wrapped continuation line in a PDF
        else:
            items.append(clean)
        evidence.append(_ev(doc, line, text))
    if field == "documents_required" and len(items) == 1 and "," in items[0]:
        items = [p.strip(" .") for p in items[0].split(",") if p.strip(" .")]
    return _cand(doc, items, evidence, 0.85), None


def _deadline(doc, sec):
    candidates = list(sec.get("deadline", []))
    note = None
    if not candidates:  # no labelled section: look for deadline wording anywhere
        candidates = [(l, l.text) for l in doc.lines if _DEADLINE_CUE.search(l.text)]
        note = "No 'Last date' label; found deadline wording in the body text."
    for line, text in candidates:
        if nz.ROLLING_RE.search(text):
            return _cand(doc, nz.ROLLING_VALUE, [_ev(doc, line, text)], 0.8, note), None
        dates = nz.find_dates(text)
        if dates:
            extra = f" Several dates in the sentence; took the first ({dates})." if len(dates) > 1 else ""
            return _cand(doc, dates[0], [_ev(doc, line, text)], 0.9 if not note else 0.7,
                         ((note or "") + extra).strip() or None), None
        rel = nz.relative_deadline(text)
        if rel:
            return _cand(doc, rel, [_ev(doc, line, text)], 0.75,
                         ((note or "") + " Relative deadline: there is no calendar date to store.").strip()), None
    return None, "No deadline stated."


def _official_link(doc, sec):
    for line, text in sec.get("official_link", []):
        m = _URL_RE.search(text)
        if m:
            return _cand(doc, m.group(0).rstrip(".,"), [_ev(doc, line, m.group(0))], 0.9), None
    for line in doc.lines:
        m = _URL_RE.search(line.text)
        if m:
            return _cand(doc, m.group(0).rstrip(".,"), [_ev(doc, line, m.group(0))], 0.5,
                         "A URL appears in the text but is not labelled as the official link."), None
    return None, ("No URL stated in the source. The address the page was captured from is not assumed "
                  "to be the application link.")
