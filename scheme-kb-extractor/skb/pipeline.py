"""Runs extraction for every scheme in the manifest and writes the draft records."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import extract_rules, verify
from .loaders import load
from .reconcile import reconcile
from .schema import FIELDS, FieldRecord, Source


def load_manifest(data_dir: Path) -> list[Source]:
    raw = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return [Source(**s) for s in raw["sources"]]


def run(data_dir: Path, out_dir: Path, mode: str = "rules") -> dict[str, list[FieldRecord]]:
    by_scheme: dict[str, list[Source]] = defaultdict(list)
    for s in load_manifest(data_dir):
        by_scheme[s.scheme_ref].append(s)

    usage_log = []
    all_records: dict[str, list[FieldRecord]] = {}
    for scheme_ref, sources in by_scheme.items():
        per_field: dict[str, list] = {f: [] for f in FIELDS}
        primary_unreadable = False
        for src in sources:
            doc = load(src, data_dir)
            if mode == "llm" and src.kind != "myscheme":
                from . import extract_llm  # imported lazily so offline mode never needs the SDK/key

                results, verify_text, usage = extract_llm.extract(doc)
                usage_log.append({"source_ref": src.source_ref, **usage})
            else:
                results, verify_text = extract_rules.extract(doc), doc.full_text
                primary_unreadable |= doc.needs_ocr and src.authority == "primary"
            results = verify.apply(results, verify_text)
            for f in FIELDS:
                cand, reason = results[f]
                per_field[f].append((src, cand, reason))
        all_records[scheme_ref] = [reconcile(scheme_ref, f, per_field[f], mode, primary_unreadable) for f in FIELDS]

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {k: [r.model_dump() for r in v] for k, v in all_records.items()}
    (out_dir / f"records_{mode}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if usage_log:
        total = sum(u["usd"] for u in usage_log)
        (out_dir / "llm_usage.json").write_text(json.dumps(
            {"calls": usage_log, "total_usd": round(total, 4), "usd_per_scheme": round(total / len(by_scheme), 4)},
            indent=2), encoding="utf-8")
    return all_records
