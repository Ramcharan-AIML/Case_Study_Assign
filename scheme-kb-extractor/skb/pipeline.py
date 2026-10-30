"""Runs extraction for every scheme in the manifest and writes the draft records."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from . import extract_rules, verify
from .loaders import load
from .reconcile import reconcile
from .schema import FIELDS, FieldRecord, Source

STALE_AFTER_DAYS = 365  # a source older than this (at capture time) gets a freshness warning


def load_manifest(data_dir: Path) -> list[Source]:
    raw = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return [Source(**s) for s in raw["sources"]]


def doc_type(src: Source, needs_ocr: bool) -> str:
    """Label used to break accuracy down by kind of document."""
    if src.kind == "pdf":
        return "Scanned PDF" if needs_ocr else "Text PDF"
    return {"html": "Web page", "text": "Press note", "myscheme": "MyScheme listing"}[src.kind]


def freshness_warning(src: Source) -> str | None:
    age = (date.fromisoformat(src.captured_at) - date.fromisoformat(src.published_on)).days
    if age > STALE_AFTER_DAYS:
        return (f"{src.source_ref} ({src.title}) was last updated {age // 30} months before capture; "
                f"its values may be out of date.")
    return None


def run(data_dir: Path, out_dir: Path, mode: str = "rules") -> dict[str, list[FieldRecord]]:
    by_scheme: dict[str, list[Source]] = defaultdict(list)
    for s in load_manifest(data_dir):
        by_scheme[s.scheme_ref].append(s)

    usage_log = []
    meta: dict = {"mode": mode, "run_at": datetime.now().isoformat(timespec="seconds"), "schemes": {}}
    if mode == "llm":
        from . import extract_llm  # imported lazily so offline mode never needs the SDK/key

        meta["models"] = {"text": extract_llm.TEXT_MODEL, "vision": extract_llm.VISION_MODEL}
    all_records: dict[str, list[FieldRecord]] = {}
    for scheme_ref, sources in by_scheme.items():
        per_field: dict[str, list] = {f: [] for f in FIELDS}
        primary_unreadable = False
        scheme_meta = {"sources": [], "warnings": [], "doc_type": None}
        for src in sources:
            doc = load(src, data_dir)
            if mode == "llm" and src.kind != "myscheme":
                results, verify_text, usage = extract_llm.extract(doc)
                usage_log += [{"source_ref": src.source_ref, **u} for u in usage]
            else:
                results, verify_text = extract_rules.extract(doc), doc.full_text
                primary_unreadable |= doc.needs_ocr and src.authority == "primary"
            results = verify.apply(results, verify_text)
            for f in FIELDS:
                cand, reason = results[f]
                per_field[f].append((src, cand, reason))
            kind = doc_type(src, doc.needs_ocr)
            scheme_meta["sources"].append({**src.model_dump(), "doc_type": kind})
            if src.authority == "primary":
                scheme_meta["doc_type"] = kind
            if warning := freshness_warning(src):
                scheme_meta["warnings"].append(warning)
        if primary_unreadable:
            scheme_meta["warnings"].append("The official document is a scan that this extractor cannot read; "
                                           "high-stakes fields are left empty.")
        all_records[scheme_ref] = [reconcile(scheme_ref, f, per_field[f], mode, primary_unreadable) for f in FIELDS]
        meta["schemes"][scheme_ref] = scheme_meta

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {k: [r.model_dump() for r in v] for k, v in all_records.items()}
    (out_dir / f"records_{mode}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if usage_log:
        total = sum(u["usd_if_paid"] for u in usage_log)
        meta["usage"] = {"calls": usage_log, "usd_if_paid_total": round(total, 5),
                         "usd_if_paid_per_scheme": round(total / len(by_scheme), 5)}
    (out_dir / f"run_{mode}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_records
