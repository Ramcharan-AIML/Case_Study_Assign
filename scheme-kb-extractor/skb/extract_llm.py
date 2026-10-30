"""LLM extractor using Claude (Anthropic API).

Model: claude-opus-5-5 ($4 / $20 per million input / output tokens).
One request per official source document. MyScheme listings are already
structured, so they go through the rule-based mapper instead (cheaper and
deterministic).

The model is asked for exact quotes, which verify.py then checks against the
source text. For a scanned PDF there is no text layer to check against, so the
model also returns its transcription; quotes are checked against that, the
confidence is capped, and the note says so. That check is weaker, and the
README is explicit about it.
"""
from __future__ import annotations

import base64
import json

import anthropic

from . import normalize as nz
from .loaders import Document
from .schema import FIELDS, LIST_FIELDS, Candidate, Evidence

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.00, 20.00  # USD per million tokens
SCANNED_CONF_CAP = 0.6

SYSTEM = """You prepare a FIRST DRAFT of a government welfare scheme record. A researcher will review every field before it reaches field agents and citizens, so an empty field with a reason is far better than a plausible guess.

For each field return:
- value: the value as stated in the document (keep the document's language; do not translate). null if the document does not state it.
- quotes: the exact text, copied character-for-character from the document, that supports the value. For list fields, one quote per item. Never paraphrase inside a quote.
- location: where the quote is (page number and section heading, e.g. "page 2, section 4. Documents Required").
- note: short reason when value is null, or anything a reviewer must know (e.g. "amount was revised; earlier amount also mentioned", "relative deadline, no calendar date").

Field rules:
- benefit_amount: the CURRENT benefit amount in rupees as written (e.g. "Rs. 1,500"). Ignore superseded/earlier amounts and income ceilings. If the document only says "as per norms", value is null.
- benefit_frequency: one of monthly, annual, one_time, instalments, or null.
- benefit_type: one of cash, in-kind, cash + in-kind, or null.
- deadline: the last date to apply as written. If applications are open all year, say so. If relative (e.g. "within 270 days of delivery"), give that phrase.
- official_link: only a URL printed in the document. Never construct or recall a URL.
- eligibility, documents_required, how_to_apply: lists of items as written.
If the document is a scanned image, first transcribe all of its text into `transcription` exactly as printed (original script), then extract. Otherwise set transcription to null."""

_FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}, {"type": "null"}]},
        "quotes": {"type": "array", "items": {"type": "string"}},
        "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["value", "quotes", "location", "note"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "transcription": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "fields": {
            "type": "object",
            "properties": {f: _FIELD_SCHEMA for f in FIELDS},
            "required": FIELDS,
            "additionalProperties": False,
        },
    },
    "required": ["transcription", "fields"],
    "additionalProperties": False,
}


def _content(doc: Document) -> list[dict]:
    if doc.source.kind == "pdf":
        b64 = base64.standard_b64encode(doc.raw_bytes).decode()
        part = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        # HTML/text: send the parsed lines with their locations, so quotes are checkable verbatim.
        listing = "\n".join(f"[{l.location}] {l.text}" for l in doc.lines)
        part = {"type": "text", "text": f"<document>\n{listing}\n</document>"}
    return [part, {"type": "text", "text": f"Source: {doc.source.title}. Extract the scheme fields."}]


def call_model(doc: Document, client: anthropic.Anthropic | None = None) -> tuple[dict, dict]:
    client = client or anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": _content(doc)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model declined {doc.source.source_ref}: {response.stop_details}")
    text = next(b.text for b in response.content if b.type == "text")
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    usage["usd"] = round(usage["input_tokens"] * PRICE_IN / 1e6 + usage["output_tokens"] * PRICE_OUT / 1e6, 4)
    return json.loads(text), usage


def to_candidates(doc: Document, raw: dict) -> tuple[dict, str]:
    """Maps the model's JSON into candidates. Returns (results, text to verify quotes against)."""
    s = doc.source
    scanned = doc.needs_ocr
    verify_text = (raw.get("transcription") or "") if scanned else doc.full_text
    results = {}
    for field in FIELDS:
        f = raw["fields"][field]
        value, quotes = f["value"], [q for q in f["quotes"] if q.strip()]
        if value in (None, "", []):
            results[field] = (None, f.get("note") or "Model found no value in this source.")
            continue
        value, problem = _normalise(field, value)
        if problem:
            results[field] = (None, f"{problem} (model said: {f['value']!r})")
            continue
        evidence = [Evidence(quote=q, location=f.get("location") or "unspecified", source_ref=s.source_ref,
                             source_link=s.link, captured_at=s.captured_at) for q in quotes]
        conf = 0.85
        note = f.get("note")
        if scanned:
            conf = SCANNED_CONF_CAP
            note = ((note or "") + " Scanned source: quote checked against the model's own transcription, "
                    "not an independent OCR. Check against the image.").strip()
        results[field] = (Candidate(value=value, evidence=evidence, confidence=conf, source_ref=s.source_ref,
                                    authority=s.authority, note=note), None)
    return results, verify_text


def _normalise(field: str, value):
    if field in LIST_FIELDS:
        return (value if isinstance(value, list) else [value]), None
    if isinstance(value, list):
        value = " ".join(value)
    if field == "benefit_amount":
        amount, _ = nz.benefit_amount(value)
        if amount is None:  # bare number such as "1500" with no currency sign
            amount, _ = nz.benefit_amount(f"Rs {value}")
        return (amount, None) if amount is not None else (None, "Could not read a rupee amount from the value.")
    if field == "deadline":
        if nz.ROLLING_RE.search(value):
            return nz.ROLLING_VALUE, None
        dates = nz.find_dates(value)
        return (dates[0] if dates else (nz.relative_deadline(value) or value)), None
    if field == "benefit_frequency":
        allowed = {"monthly", "annual", "one_time", "instalments"}
        v = value.strip().lower().replace("-", "_").replace(" ", "_")
        return (v, None) if v in allowed else (nz.frequency(value)[0], None)
    return value.strip(), None


def extract(doc: Document, client: anthropic.Anthropic | None = None) -> tuple[dict, str, dict]:
    raw, usage = call_model(doc, client)
    results, verify_text = to_candidates(doc, raw)
    return results, verify_text, usage
