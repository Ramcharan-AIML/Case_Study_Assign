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


def evaluate(records: dict[str, list[dict]], gold: dict) -> dict:
    rows = []
    for scheme_ref, recs in records.items():
        if scheme_ref not in gold:
            continue
        for rec in recs:
            g = gold[scheme_ref][rec["field"]]
            rows.append({"scheme_ref": scheme_ref, "field": rec["field"], "outcome": outcome(rec["field"], rec, g),
                         "pred_status": rec["status"], "gold_status": g["status"], "confidence": rec["confidence"]})

    per_field = defaultdict(Counter)
    for r in rows:
        per_field[r["field"]][r["outcome"]] += 1
    total = Counter(r["outcome"] for r in rows)
    n = len(rows)

    def rate(c: Counter, keys) -> float:
        m = sum(c.values())
        return round(sum(c[k] for k in keys) / m, 3) if m else 0.0

    hs = Counter(r["outcome"] for r in rows if r["field"] in HIGH_STAKES)
    return {
        "n_fields": n,
        "accuracy": rate(total, GOOD),
        "dangerous_error_rate": rate(total, DANGEROUS),
        "safe_error_rate": rate(total, SAFE_ERRORS),
        "high_stakes_accuracy": rate(hs, GOOD),
        "high_stakes_dangerous_rate": rate(hs, DANGEROUS),
        "outcomes": dict(total),
        "per_field": {f: {"n": sum(per_field[f].values()), "accuracy": rate(per_field[f], GOOD),
                          "dangerous": sum(per_field[f][k] for k in DANGEROUS),
                          "safe_errors": sum(per_field[f][k] for k in SAFE_ERRORS)} for f in FIELDS},
        "rows": rows,
    }


def to_markdown(result: dict, mode: str) -> str:
    out = [f"# Evaluation report ({mode} extractor)\n",
           f"Fields checked: **{result['n_fields']}** across {len({r['scheme_ref'] for r in result['rows']})} schemes.\n",
           "| Measure | Value | In plain words |", "|---|---|---|",
           f"| Field-level accuracy | {result['accuracy']:.0%} | Share of fields a researcher can accept without retyping |",
           f"| Dangerous error rate | {result['dangerous_error_rate']:.0%} | Share of fields that are wrong but look fine |",
           f"| Safe error rate | {result['safe_error_rate']:.0%} | Share left empty or over-flagged (costs reviewer time only) |",
           f"| High-stakes accuracy | {result['high_stakes_accuracy']:.0%} | Accuracy on amount, frequency, deadline, documents and eligibility |",
           f"| High-stakes dangerous rate | {result['high_stakes_dangerous_rate']:.0%} | Must be ~0 before scaling |",
           "", "## Per field", "", "| Field | n | Accuracy | Dangerous | Safe errors |", "|---|---|---|---|---|"]
    for f, v in result["per_field"].items():
        flag = " ⚠" if v["dangerous"] else ""
        out.append(f"| {f}{flag} | {v['n']} | {v['accuracy']:.0%} | {v['dangerous']} | {v['safe_errors']} |")
    out += ["", "## Every field that was not correct", "", "| Scheme | Field | Outcome | Draft said | Truth |", "|---|---|---|---|---|"]
    for r in result["rows"]:
        if r["outcome"] not in GOOD:
            out.append(f"| {r['scheme_ref']} | {r['field']} | **{r['outcome']}** | {r['pred_status']} | {r['gold_status']} |")
    return "\n".join(out) + "\n"
