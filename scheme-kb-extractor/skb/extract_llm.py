"""LLM extractor using Groq (free tier available at console.groq.com).

Two open-weight models, both served by Groq:
  - openai/gpt-oss-120b     reads the document text and fills the fields (text only)
  - Llama 4 Scout (vision)  only for scanned pages: transcribes the image to text first

Why the split: GPT-OSS cannot see images. Instead of guessing from a scan, we
transcribe it with a vision model, then extract from that transcription.

Every document is sent as numbered lines ("[page 1, line 9] ..."), so the model
can cite a location and verify.py can check each quote word-for-word against
the very same text. Model names can be overridden with environment variables
because hosted model line-ups change.
"""
from __future__ import annotations

import base64
import json
import os

import pymupdf
from pydantic import BaseModel, ValidationError

from . import normalize as nz
from .loaders import Document
from .schema import FIELDS, LIST_FIELDS, Candidate, Evidence

TEXT_MODEL = os.getenv("SKB_GROQ_MODEL", "openai/gpt-oss-120b")
VISION_MODEL = os.getenv("SKB_GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
# Groq on-demand list prices in USD per million tokens (input, output), used only for the
# cost estimate. The free tier costs nothing but is rate-limited. Check groq.com/pricing.
PRICES = {TEXT_MODEL: (0.15, 0.60), VISION_MODEL: (0.11, 0.34)}
SCANNED_CONF_CAP = 0.6

SYSTEM = """You prepare a FIRST DRAFT of a government welfare scheme record. A researcher reviews every field before it reaches field agents and citizens, so an empty field with a reason is far better than a plausible guess.

The document is given as lines, each prefixed with its location in square brackets.

Return ONLY a JSON object of this exact shape:
{"fields": {"<field>": {"value": <string | list of strings | null>, "quotes": [<string>], "location": <string | null>, "note": <string | null>}}}
with exactly these field keys: scheme_name, department, benefit_type, benefit_amount, benefit_frequency, eligibility, documents_required, how_to_apply, deadline, official_link.

For each field:
- value: as stated in the document, in the document's language (do not translate). null if not stated.
- quotes: exact text copied character-for-character from the document lines (without the [location] prefix) that supports the value. One quote per item for list fields. Never paraphrase.
- location: the bracketed location of the quote, e.g. "page 2, line 7".
- note: short reason when value is null, or anything a reviewer must know.

Field rules:
- benefit_amount: the CURRENT benefit in rupees as written (e.g. "Rs. 1,500"). Ignore earlier/superseded amounts and income ceilings. If the document only says "as per norms", value is null.
- benefit_frequency: one of monthly, annual, one_time, instalments, or null.
- benefit_type: one of cash, in-kind, cash + in-kind, or null.
- deadline: last date to apply as written; if applications are open all year say so; if relative (e.g. "within 270 days of delivery") give that phrase.
- official_link: only a URL printed in the document. Never construct or recall a URL.
- eligibility, documents_required, how_to_apply: lists of items as written."""

TRANSCRIBE_PROMPT = ("Transcribe ALL text on this scanned government document page exactly as printed, in its "
                     "original script (do not translate), one printed line per output line. Output only the text.")


class _Field(BaseModel):
    value: str | list[str] | None = None
    quotes: list[str] = []
    location: str | None = None
    note: str | None = None


class _Output(BaseModel):
    fields: dict[str, _Field]


def _client():
    from groq import Groq  # imported lazily so offline mode never needs the SDK

    return Groq()  # reads GROQ_API_KEY


def _usage(model: str, resp) -> dict:
    p_in, p_out = PRICES.get(model, (0.0, 0.0))
    u = resp.usage
    return {"model": model, "input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens,
            "usd_if_paid": round(u.prompt_tokens * p_in / 1e6 + u.completion_tokens * p_out / 1e6, 5)}


def transcribe_scan(doc: Document, client) -> tuple[list[str], list[dict]]:
    """Scanned PDF -> lines '[scan page N, line i] text' via the vision model."""
    lines, usage = [], []
    with pymupdf.open(stream=doc.raw_bytes, filetype="pdf") as pdf:
        for pno, page in enumerate(pdf, start=1):
            png = page.get_pixmap(dpi=150).tobytes("png")
            url = "data:image/png;base64," + base64.b64encode(png).decode()
            resp = client.chat.completions.create(
                model=VISION_MODEL, temperature=0,
                messages=[{"role": "user", "content": [{"type": "text", "text": TRANSCRIBE_PROMPT},
                                                       {"type": "image_url", "image_url": {"url": url}}]}])
            usage.append(_usage(VISION_MODEL, resp))
            text = resp.choices[0].message.content or ""
            lines += [f"[scan page {pno}, line {i}] {t.strip()}"
                      for i, t in enumerate(text.splitlines(), start=1) if t.strip()]
    return lines, usage


def call_model(numbered_lines: list[str], title: str, client) -> tuple[dict, dict]:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Source: {title}\n<document>\n" + "\n".join(numbered_lines) + "\n</document>"}]
    for attempt in range(2):  # one retry if the JSON does not match the expected shape
        resp = client.chat.completions.create(model=TEXT_MODEL, temperature=0, messages=messages,
                                              response_format={"type": "json_object"})
        content = resp.choices[0].message.content or ""
        try:
            parsed = _Output.model_validate_json(content)
            missing = [f for f in FIELDS if f not in parsed.fields]
            if missing:
                raise ValueError(f"missing fields {missing}")
            return {"fields": {f: parsed.fields[f].model_dump() for f in FIELDS}}, _usage(TEXT_MODEL, resp)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That JSON was invalid ({e}). Return the corrected JSON only."}]
    raise RuntimeError(f"Model did not return valid JSON for {title}")


def to_candidates(doc: Document, raw: dict) -> dict:
    """Maps the model's JSON into candidates (quotes are checked later by verify.py)."""
    s, scanned = doc.source, doc.needs_ocr
    results = {}
    for field in FIELDS:
        f = raw["fields"][field]
        value, quotes = f["value"], [q for q in f["quotes"] if q and q.strip()]
        if value in (None, "", []):
            results[field] = (None, f.get("note") or "Model found no value in this source.")
            continue
        value, problem = _normalise(field, value)
        if problem:
            results[field] = (None, f"{problem} (model said: {f['value']!r})")
            continue
        evidence = [Evidence(quote=q, location=f.get("location") or "unspecified", source_ref=s.source_ref,
                             source_link=s.link, captured_at=s.captured_at) for q in quotes]
        conf, note = 0.85, f.get("note")
        if scanned:
            conf = SCANNED_CONF_CAP
            note = ((note or "") + " Scanned source: quote checked against the vision model's transcription, "
                    "not the image itself. Compare with the scan.").strip()
        results[field] = (Candidate(value=value, evidence=evidence, confidence=conf, source_ref=s.source_ref,
                                    authority=s.authority, note=note), None)
    return results


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
        v = value.strip().lower().replace("-", "_").replace(" ", "_")
        return (v, None) if v in {"monthly", "annual", "one_time", "instalments"} else (nz.frequency(value)[0], None)
    return value.strip(), None


def extract(doc: Document, client=None) -> tuple[dict, str, list[dict]]:
    client = client or _client()
    usage: list[dict] = []
    if doc.needs_ocr:
        numbered, usage = transcribe_scan(doc, client)
    else:
        numbered = [f"[{l.location}] {l.text}" for l in doc.lines]
    # Quotes are verified against the text the model actually saw (minus the location prefixes).
    verify_text = "\n".join(line.split("] ", 1)[1] if "] " in line else line for line in numbered)
    raw, u = call_model(numbered, doc.source.title, client)
    usage.append(u)
    return to_candidates(doc, raw), verify_text, usage
