"""Command line entry point.

    python -m skb run   [--mode rules|llm]   extract -> out/records_<mode>.json + out/review.html
    python -m skb eval  [--mode ...]         score against the answer key -> out/eval_<mode>.md
    python -m skb all   [--mode ...]         run + eval + review screen
    python -m skb import-decisions FILE      add exported reviewer decisions to the answer key
    python -m skb samples                    regenerate the sample PDFs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "out"


def _run(mode: str) -> None:
    from . import pipeline

    records = pipeline.run(DATA, OUT, mode)
    for scheme, recs in records.items():
        counts = {s: sum(r.status == s for r in recs) for s in ("found", "conflict", "not_found")}
        print(f"{scheme}: {counts['found']} found, {counts['conflict']} conflict, {counts['not_found']} not found")
    meta = json.loads((OUT / f"run_{mode}.json").read_text(encoding="utf-8"))
    if "usage" in meta:
        print(f"\nGroq usage: ${meta['usage']['usd_if_paid_per_scheme']} per scheme at paid rates (free tier: $0)")
    print(f"\nDraft records: {OUT / f'records_{mode}.json'}")


def _source_texts() -> dict[str, str]:
    from .loaders import load
    from .pipeline import load_manifest

    docs = [load(s, DATA) for s in load_manifest(DATA)]
    return {d.source.source_ref: d.full_text for d in docs if not d.needs_ocr}


def _eval(mode: str) -> None:
    from .evaluate import evaluate, to_markdown
    from .feedback import merged_gold

    records = json.loads((OUT / f"records_{mode}.json").read_text(encoding="utf-8"))
    meta = json.loads((OUT / f"run_{mode}.json").read_text(encoding="utf-8"))
    result = evaluate(records, merged_gold(DATA), meta, _source_texts())
    md = to_markdown(result, mode)
    (OUT / f"eval_{mode}.md").write_text(md, encoding="utf-8")
    (OUT / f"eval_{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(md)


def _review(mode: str) -> None:
    from . import review

    review.build(OUT, mode)
    print(f"Review screen: {OUT / 'review.html'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 and choke on Devanagari
    p = argparse.ArgumentParser(prog="skb", description="Scheme field extraction with evidence")
    p.add_argument("command", choices=["samples", "run", "eval", "all", "import-decisions"])
    p.add_argument("file", nargs="?", help="review_decisions.json (for import-decisions)")
    p.add_argument("--mode", choices=["rules", "llm"], default="rules",
                   help="rules = offline baseline (default); llm = Groq GPT-OSS, needs GROQ_API_KEY")
    args = p.parse_args()
    if args.command == "samples":
        from .samples import main as make
        make()
    if args.command == "import-decisions":
        from .feedback import import_decisions

        if not args.file:
            p.error("give the path to review_decisions.json")
        counts = import_decisions(Path(args.file), OUT / f"records_{args.mode}.json", DATA / "gold_reviewed.json")
        print(f"Added to data/gold_reviewed.json: {counts}. Run `python -m skb eval` to re-score.")
    if args.command in ("run", "all"):
        _run(args.mode)
    if args.command in ("eval", "all"):
        _eval(args.mode)
    if args.command in ("run", "eval", "all"):
        _review(args.mode)


if __name__ == "__main__":
    main()
