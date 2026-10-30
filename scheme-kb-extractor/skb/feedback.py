"""Turns reviewer decisions (exported from the review screen) into test answers.

This is the loop the brief asks about: every time a researcher approves or
corrects a field, that becomes a checked answer, so the test set grows with
exactly the cases the extractor finds hard. Reviewed answers are kept in
data/gold_reviewed.json and override the hand-written data/gold.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .normalize import benefit_amount
from .schema import LIST_FIELDS


def _parse(field: str, value):
    if value is None or not isinstance(value, str):
        return value
    if field in LIST_FIELDS:
        return [p.strip() for p in re.split(r"[;\n|]", value) if p.strip()]
    if field == "benefit_amount":
        amount, _ = benefit_amount(value if re.search(r"₹|Rs|रु", value) else f"Rs {value}")
        return amount
    return value.strip()


def to_gold_entry(d: dict, record: dict | None) -> dict:
    entry = {"origin": "reviewer", "reviewed_at": d.get("reviewed_at")}
    decision = d["decision"]
    if decision == "confirmed empty":
        return {**entry, "status": "not_found"}
    if decision == "conflict resolved" and record and record["status"] == "conflict":
        # The extraction was right to flag it; keep it a conflict and remember what the reviewer chose.
        return {**entry, "status": "conflict", "candidates": [c["value"] for c in record["candidates"]],
                "resolved_value": d["value"]}
    return {**entry, "status": "found", "value": _parse(d["field"], d["value"])}


def import_decisions(decisions_path: Path, records_path: Path, reviewed_path: Path) -> dict:
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    records = json.loads(records_path.read_text(encoding="utf-8"))
    index = {(s, r["field"]): r for s, recs in records.items() for r in recs}
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8")) if reviewed_path.exists() else {}
    counts = {"approved": 0, "corrected": 0, "confirmed empty": 0, "conflict resolved": 0}
    for d in decisions:
        reviewed.setdefault(d["scheme_ref"], {})[d["field"]] = to_gold_entry(d, index.get((d["scheme_ref"], d["field"])))
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    reviewed_path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def merged_gold(data_dir: Path) -> dict:
    gold = json.loads((data_dir / "gold.json").read_text(encoding="utf-8"))
    reviewed_path = data_dir / "gold_reviewed.json"
    if reviewed_path.exists():
        for scheme, fields in json.loads(reviewed_path.read_text(encoding="utf-8")).items():
            gold.setdefault(scheme, {}).update(fields)
    return gold
