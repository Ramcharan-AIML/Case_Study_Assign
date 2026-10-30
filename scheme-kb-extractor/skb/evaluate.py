"""Field-level accuracy against a hand-checked gold set.

Every (scheme, field) pair gets exactly one outcome:

  correct          value matches the checked answer
  correct_empty    both say "not in the source"
  conflict_caught  sources disagree and every disagreeing value was surfaced
  missed           answer exists but the draft left it empty     (safe: costs reviewer time)
  false_conflict   draft flagged a conflict that isn't one        (safe: costs reviewer time)
  wrong_value      draft filled in the wrong value                (DANGEROUS)
  false_fill       draft filled in a value the source never gave  (DANGEROUS)
  conflict_missed  sources disagree but draft showed only one     (DANGEROUS: silent pick)

"Dangerous" = a reviewer who skims could approve it and it would reach a citizen.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .compare import values_equal
from .schema import FIELDS, HIGH_STAKES

GOOD = {"correct", "correct_empty", "conflict_caught"}
DANGEROUS = {"wrong_value", "false_fill", "conflict_missed"}
SAFE_ERRORS = {"missed", "false_conflict"}


def _matches(field: str, pred, gold: dict) -> bool:
    options = [gold.get("value")] + gold.get("accept", [])
    return any(values_equal(field, pred, o) for o in options if o is not None)


def outcome(field: str, pred: dict, gold: dict) -> str:
    gs, ps = gold["status"], pred["status"]
    if gs == "conflict":
        if ps == "not_found":
            return "missed"  # nothing pre-filled, so nothing can mislead the reviewer
        if ps != "conflict":
            return "conflict_missed"
        pvals = [c["value"] for c in pred["candidates"]]
        all_surfaced = all(any(values_equal(field, p, g) for p in pvals) for g in gold["candidates"])
        return "conflict_caught" if all_surfaced and len(pvals) == len(gold["candidates"]) else "conflict_missed"
    if gs == "found":
        if ps == "found":
            return "correct" if _matches(field, pred["value"], gold) else "wrong_value"
        return "missed" if ps == "not_found" else "false_conflict"
    return "correct_empty" if ps == "not_found" else "false_fill"


def evaluate(records: dict[str, list[dict]], gold: dict, meta: dict | None = None,
             source_texts: dict[str, str] | None = None) -> dict:
    """meta: run_<mode>.json (gives each scheme's document type).
    source_texts: source_ref -> text, used to re-check that every quote really exists."""
    doc_types = {k: v.get("doc_type") for k, v in (meta or {}).get("schemes", {}).items()}
    rows = []
    for scheme_ref, recs in records.items():
        if scheme_ref not in gold:
            continue
        for rec in recs:
            g = gold[scheme_ref][rec["field"]]
            rows.append({"scheme_ref": scheme_ref, "field": rec["field"], "outcome": outcome(rec["field"], rec, g),
                         "pred_status": rec["status"], "gold_status": g["status"], "confidence": rec["confidence"],
                         "doc_type": doc_types.get(scheme_ref, "unknown")})

    def rate(c: Counter, keys) -> float:
        m = sum(c.values())
        return round(sum(c[k] for k in keys) / m, 3) if m else 0.0

    per_field, per_type = defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        per_field[r["field"]][r["outcome"]] += 1
        per_type[r["doc_type"]][r["outcome"]] += 1
    total = Counter(r["outcome"] for r in rows)
    hs = Counter(r["outcome"] for r in rows if r["field"] in HIGH_STAKES)
    gold_conflicts = [r for r in rows if r["gold_status"] == "conflict"]

    result = {
        "n_fields": len(rows),
        "n_schemes": len({r["scheme_ref"] for r in rows}),
        "accuracy": rate(total, GOOD),
        "dangerous_error_rate": rate(total, DANGEROUS),
        "safe_error_rate": rate(total, SAFE_ERRORS),
        "high_stakes_accuracy": rate(hs, GOOD),
        "high_stakes_dangerous_rate": rate(hs, DANGEROUS),
        "conflict_recall": round(sum(r["outcome"] == "conflict_caught" for r in gold_conflicts) / len(gold_conflicts), 3)
        if gold_conflicts else None,
        "n_conflicts": len(gold_conflicts),
        "grounding_rate": grounding_rate(records, source_texts) if source_texts else None,
        "outcomes": dict(total),
        "per_field": {f: _summary(per_field[f], rate) for f in FIELDS},
        "per_doc_type": {t: _summary(c, rate) for t, c in sorted(per_type.items())},
        "rows": rows,
    }
    result["readiness"] = readiness(result)
    return result


def _summary(c: Counter, rate) -> dict:
    return {"n": sum(c.values()), "accuracy": rate(c, GOOD), "dangerous": sum(c[k] for k in DANGEROUS),
            "safe_errors": sum(c[k] for k in SAFE_ERRORS)}


def grounding_rate(records: dict, source_texts: dict[str, str]) -> float:
    """Share of filled-in values whose every quote is found in its (readable) source."""
    from .verify import _squash

    texts = {k: _squash(v) for k, v in source_texts.items()}
    checked = grounded = 0
    for recs in records.values():
        for rec in recs:
            groups = [c["evidence"] for c in rec["candidates"]] if rec["status"] == "conflict" else \
                [rec["evidence"]] if rec["status"] == "found" else []
            for evidence in groups:
                quotes = [e for e in evidence if e["source_ref"] in texts]
                if not quotes:
                    continue  # e.g. scanned source: no independent text to check against
                checked += 1
                grounded += all(_squash(e["quote"]) in texts[e["source_ref"]] for e in quotes)
    return round(grounded / checked, 3) if checked else 1.0


# The go/no-go bar proposed in the README, checked automatically.
THRESHOLDS = [
    ("Test set is big enough", "n_schemes", ">=", 100, "Need ~100 real, held-out schemes before trusting the numbers"),
    ("No dangerous errors on high-stakes fields", "high_stakes_dangerous_rate", "<=", 0.01, "Wrong money/date/document values that look right"),
    ("Every value has a real quote", "grounding_rate", ">=", 1.0, "Enforced by code; this is a regression check"),
    ("Conflicts are caught", "conflict_recall", ">=", 0.95, "Disagreements between sources must be surfaced"),
    ("Checking beats typing", "accuracy", ">=", 0.80, "Below this, reviewers would be faster typing from scratch"),
]


def readiness(result: dict) -> dict:
    checks = []
    for name, key, op, target, why in THRESHOLDS:
        actual = result.get(key)
        passed = actual is not None and (actual >= target if op == ">=" else actual <= target)
        checks.append({"check": name, "metric": key, "rule": f"{op} {target}", "actual": actual, "passed": passed, "why": why})
    return {"ready": all(c["passed"] for c in checks), "checks": checks}


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def to_markdown(result: dict, mode: str) -> str:
    ready = result["readiness"]
    out = [f"# Evaluation report ({mode} extractor)\n",
           f"Fields checked: **{result['n_fields']}** across {result['n_schemes']} schemes.\n",
           "| Measure | Value | In plain words |", "|---|---|---|",
           f"| Field-level accuracy | {_pct(result['accuracy'])} | Share of fields a researcher can accept without retyping |",
           f"| Dangerous error rate | {_pct(result['dangerous_error_rate'])} | Share of fields that are wrong but look fine |",
           f"| Safe error rate | {_pct(result['safe_error_rate'])} | Share left empty or over-flagged (costs reviewer time only) |",
           f"| High-stakes accuracy | {_pct(result['high_stakes_accuracy'])} | Accuracy on amount, frequency, deadline, documents and eligibility |",
           f"| High-stakes dangerous rate | {_pct(result['high_stakes_dangerous_rate'])} | Must be ~0 before scaling |",
           f"| Conflict recall | {_pct(result['conflict_recall'])} | Of {result['n_conflicts']} real disagreements, how many were shown |",
           f"| Grounding rate | {_pct(result['grounding_rate'])} | Filled values whose quote really is in the source |",
           "", f"## Ready to scale to 5,000 schemes? **{'YES' if ready['ready'] else 'NOT YET'}**", "",
           "| Check | Rule | Actual | Result |", "|---|---|---|---|"]
    for c in ready["checks"]:
        actual = c["actual"] if c["metric"] == "n_schemes" else _pct(c["actual"])
        out.append(f"| {c['check']} | {c['metric']} {c['rule']} | {actual} | {'PASS' if c['passed'] else 'FAIL'} |")
    out += ["", "## By document type", "", "| Document type | Fields | Accuracy | Dangerous | Safe errors |", "|---|---|---|---|---|"]
    for t, v in result["per_doc_type"].items():
        out.append(f"| {t} | {v['n']} | {_pct(v['accuracy'])} | {v['dangerous']} | {v['safe_errors']} |")
    out += ["", "## By field", "", "| Field | n | Accuracy | Dangerous | Safe errors |", "|---|---|---|---|---|"]
    for f, v in result["per_field"].items():
        flag = " ⚠" if v["dangerous"] else ""
        out.append(f"| {f}{flag} | {v['n']} | {_pct(v['accuracy'])} | {v['dangerous']} | {v['safe_errors']} |")
    out += ["", "## Every field that was not correct", "", "| Scheme | Field | Outcome | Draft said | Truth |", "|---|---|---|---|---|"]
    for r in result["rows"]:
        if r["outcome"] not in GOOD:
            out.append(f"| {r['scheme_ref']} | {r['field']} | **{r['outcome']}** | {r['pred_status']} | {r['gold_status']} |")
    return "\n".join(out) + "\n"
