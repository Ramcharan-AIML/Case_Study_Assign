"""Command line entry point.

    python -m skb samples             regenerate the binary sample PDFs
    python -m skb run [--mode rules|llm]   extract -> out/records_<mode>.json + out/review.html
    python -m skb eval [--mode ...]   score against data/gold.json -> out/eval_<mode>.md
    python -m skb all [--mode ...]    run + eval
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "out"


def _run(mode: str) -> None:
    from . import pipeline, review

    records = pipeline.run(DATA, OUT, mode)
    review.build(OUT / f"records_{mode}.json", DATA, OUT / "review.html", mode)
    for scheme, recs in records.items():
        counts = {s: sum(r.status == s for r in recs) for s in ("found", "conflict", "not_found")}
        print(f"{scheme}: {counts['found']} found, {counts['conflict']} conflict, {counts['not_found']} not found")
    print(f"\nDraft records: {OUT / f'records_{mode}.json'}\nReview screen: {OUT / 'review.html'}")
    if (OUT / "llm_usage.json").exists() and mode == "llm":
        print("LLM cost:", json.loads((OUT / "llm_usage.json").read_text())["usd_per_scheme"], "USD per scheme")


def _eval(mode: str) -> None:
    from .evaluate import evaluate, to_markdown

    records = json.loads((OUT / f"records_{mode}.json").read_text(encoding="utf-8"))
    gold = json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
    result = evaluate(records, gold)
    md = to_markdown(result, mode)
    (OUT / f"eval_{mode}.md").write_text(md, encoding="utf-8")
    (OUT / f"eval_{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(md)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 and choke on Devanagari
    p = argparse.ArgumentParser(prog="skb", description="Scheme field extraction with evidence")
    p.add_argument("command", choices=["samples", "run", "eval", "all"])
    p.add_argument("--mode", choices=["rules", "llm"], default="rules",
                   help="rules = offline baseline (default); llm = Claude, needs ANTHROPIC_API_KEY")
    args = p.parse_args()
    if args.command == "samples":
        from .samples import main as make
        make()
    if args.command in ("run", "all"):
        _run(args.mode)
    if args.command in ("eval", "all"):
        _eval(args.mode)


if __name__ == "__main__":
    main()
