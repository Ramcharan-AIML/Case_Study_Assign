# Scheme field extraction with evidence (Case study A1)

AI prepares a **first draft** of a scheme record from government documents. Every value carries the exact
quote, the page or section and the source it came from. When sources disagree, the draft keeps both values
and does not pick one. A researcher checks every field in a review console before anything can be published.

```bash
pip install -r requirements.txt
python -m skb all                 # offline: extract -> evaluate -> review console (no API key needed)
python -m pytest -q               # 15 edge-case tests
# then open out/review.html in a browser (tabs: Review · Accuracy · How it works)
```

Optional AI mode, using Groq's free tier: create a key at console.groq.com, set `GROQ_API_KEY`, then run
`python -m skb all --mode llm` (see [§6 Model and cost](#6-model-and-cost)).

---

## 1. How it works

```
 official PDF / scanned PDF / web page / press note        MyScheme listing
                 │                                                │
           loaders.py  ── every line keeps its page / section ────┘
                 │
     ┌───────────┴─────────────────────────┐
 extract_rules.py                 extract_llm.py (Groq)
 (offline baseline,               scan? → Llama 4 Scout (vision) transcribes the page
  default)                        text  → GPT-OSS-120B fills the fields with quotes
     └───────────┬─────────────────────────┘
           verify.py   ── a value survives only if its quote is literally in the source
                 │
          reconcile.py ── agree → found · disagree → CONFLICT (both kept) · official doc unreadable → empty
                 │          + freshness warning when a source is over 12 months old
   out/records_*.json ──► out/review.html  (Review: approve / correct / pick a side; timed)
                 │                    │ Export decisions → `python -m skb import-decisions`
           evaluate.py ◄── data/gold.json + data/gold_reviewed.json (answer key that grows from reviews)
                 │
     accuracy · dangerous errors · conflict recall · grounding rate · by doc type · READINESS GATE
```

Three rules are built into the code, not left to the model:

1. **No quote, no value.** `verify.py` drops any value whose quote cannot be found in the source text, and records why.
2. **Never pick a side silently.** Disagreeing sources produce `status: "conflict"`, with every value and its own evidence kept. The note gives publication dates so the reviewer can decide quickly.
3. **Never present a guess.** An unreadable document gives "not found, here's why". It never falls back to a plausible value.

## 2. Sample documents and the tricky case each one tests

All synthetic. "Vindhyachal" is a fictional state. Links use the reserved `.example` domain or `synthetic://` placeholders.

| Scheme | Sources | What it tests |
|---|---|---|
| **SCH001** Old-age pension | English 2-page text **PDF** + **MyScheme** listing | **Conflict.** The notification revised the pension from ₹1,000 to ₹1,500, but MyScheme still shows ₹1,000 and last year's deadline, and it omits one required document. The same PDF mentions the *earlier* ₹1,000 and an *income ceiling* of ₹1,20,000; neither should be taken as the benefit. Fields are spread across two pages. |
| **SCH002** Girl-child education incentive | **Hindi** department **web page** | Devanagari digits (₹ १०,०००), "एकमुश्त" (one-time), **no fixed deadline** ("आवेदन पूरे वर्ष खुले रहते हैं"), and **no official link**. The link must stay empty; the page's own address is not assumed to be one. |
| **SCH003** Widow assistance | **Scanned Marathi PDF** (image only, no text layer, tilted, noisy) + partial MyScheme | **Unreadable official source.** MyScheme shows an outdated ₹1,000 against ₹1,200 in the circular, and the listing is 16 months old, which triggers a **freshness warning**. The name appears in two scripts. |
| **SCH004** Maternal nutrition | English **press note** + MyScheme | **Vague source.** The amount is "as per the norms prescribed", so the document gives no figure; only MyScheme gives ₹5,000. There's a **relative deadline** ("within 270 days of delivery"), no "Scheme name:" label (the name comes from the headline), and a cash + in-kind benefit. |

You can view the scan at `data/sources/SCH003_widow_assistance_scan_mr.png`.

## 3. Results

`python -m skb all` gives this report (full version in `out/eval_rules.md`, and in the console's **Accuracy** tab):

| Measure (offline extractor, 40 fields) | Value |
|---|---|
| Field-level accuracy | **85%** |
| Dangerous error rate (wrong value that looks fine) | **0%** |
| Safe error rate (left empty, so the reviewer fills it in) | 15% |
| Conflict recall (disagreements surfaced) | 75% (3 of 4) |
| Grounding rate (values whose quote is really in the source) | 100% |
| **Readiness to scale** | **NOT YET**: 3 of 5 checks pass |

| By document type | Accuracy | Dangerous |
|---|---|---|
| Text PDF / web page (Hindi) / press note | 100% | 0 |
| Scanned PDF (Marathi) | 40% | 0 |

**How to read this honestly:**
- All 6 misses, and the one missed conflict, are in **SCH003, the scanned Marathi circular**. The offline extractor has no OCR, so it correctly refuses to read the scan. The Groq mode reads scans through a vision model.
- On the three text documents the offline extractor is 100% correct. **This does not show that the extractor is good.** I wrote both the documents and the rules, so this only shows that the pipeline (evidence, verification, conflicts, review, scoring) works end to end.
- **The system itself says "not ready".** The readiness gate fails on test-set size (4 schemes, not about 100) and on conflict recall. That is the intended behaviour: the gate should only pass on real, held-out data.
- **A change made because of the evaluation:** the first version showed MyScheme's stale ₹1,000 for SCH003 as "found (low confidence)". The evaluator flagged it as a *dangerous* error, because a tired reviewer could approve it. Now, when the official document exists but can't be read, high-stakes fields stay empty and the MyScheme value appears only as an "unverified hint". Accuracy fell from 88% to 85%; dangerous errors fell from 2% to 0%. I'd make that trade every time.

## 4. Field format

Each field is one record, as in the brief, with one addition: `candidates`, which holds every value in a conflict.
Here is a real output (`out/records_rules.json`):

```json
{
  "scheme_ref": "SCH001",
  "field": "benefit_amount",
  "value": null,
  "status": "conflict",
  "confidence": 0.3,
  "note": "Sources disagree; not auto-resolved. 1500 from SRC-001-A (primary, published 2026-03-12) vs 1000 from SRC-001-M (secondary, published 2025-11-02). Reviewer hint: the most recently published source is SRC-001-A.",
  "candidates": [
    {"value": 1500, "source_ref": "SRC-001-A", "confidence": 0.9,
     "note": "Ignored other amounts: Rs 1000 (preceded by 'revises').",
     "evidence": [{"quote": "Monthly pension of Rs. 1,500 (Rupees One Thousand Five Hundred only) per month,",
                   "location": "page 1, line 7", "source_ref": "SRC-001-A",
                   "source_link": "synthetic://vindhyachal/sje/notification-SJE-PEN-2026-114.pdf",
                   "captured_at": "2026-10-28"}]},
    {"value": 1000, "source_ref": "SRC-001-M", "confidence": 0.9,
     "evidence": [{"quote": "Monthly pension of ₹1,000 per month credited to the beneficiary's bank account through DBT.",
                   "location": "MyScheme listing, section 'Benefits'", "source_ref": "SRC-001-M", "...": "..."}]}
  ]
}
```

Normalised values make fields comparable across sources and languages: amounts are integer rupees;
frequency is one of `monthly | annual | one_time | instalments`; deadlines are ISO dates, or the text
"No fixed deadline…" or "Within N days of …"; documents map to canonical codes, so "आधार कार्ड" equals "Aadhaar card".

## 5. Measuring accuracy, and when it is good enough for 5,000 schemes

**What "field-level accuracy" means, in programme terms:**
> Out of every 100 fields the AI pre-fills, how many can the researcher accept as they are, without retyping?

That number alone is not enough, because errors differ. So every field gets exactly one outcome:

| Outcome | Example | Effect |
|---|---|---|
| correct / correctly empty / conflict caught | ₹1,500 vs ₹1,000 both shown | Researcher saves time |
| **missed** (left empty) | Scan not read | Researcher types it, same as today. **Safe.** |
| **false conflict** | Same value flagged twice | A few seconds to dismiss. **Safe.** |
| **wrong value**, **invented value**, **conflict hidden** | Stale ₹1,000 shown as fact | Could reach a citizen if the reviewer skims. **Dangerous.** |

**The readiness gate.** This is checked automatically on every run (`skb/evaluate.py → THRESHOLDS`), shown in the report and in the Accuracy tab:

| Check | Rule | Why |
|---|---|---|
| Test set is big enough | ≥ 100 held-out real schemes | Fewer and the numbers are noise |
| No dangerous errors on high-stakes fields | ≤ 1% on amount, frequency, deadline, documents, eligibility | These cost families money |
| Every value has a real quote | grounding rate = 100% | Enforced by code; regression check |
| Conflicts are caught | conflict recall ≥ 95% | Hidden disagreements are silent errors |
| Checking beats typing | accuracy ≥ 80% | Below this, reviewers type faster from scratch |

**Process before running on 5,000:**
1. **Build the test set from real work.** Take about 100 schemes researchers have already entered by hand, stratified by document type (text PDF, scan, web page, Hindi, Marathi and other languages) and by central vs state. Their checked entries become `gold.json`; hold out about 30 that nobody tunes prompts on.
2. **Pass the gate on every document type**, not only overall. The report breaks accuracy down by type for this reason: one bad type (scans) can hide inside a good average.
3. **Time it.** The review console times each scheme from opening to the last decision, and the time is included in the exported decisions. In a pilot, compare that with the time to type the same scheme from scratch.
4. **Roll out in stages** (200, then 1,000, then the rest), re-scoring a 5% random sample at each stage. Exported reviewer decisions are imported with `python -m skb import-decisions review_decisions.json` into `data/gold_reviewed.json`, so the answer key keeps growing with real failure cases.

## 6. Model and cost

| | |
|---|---|
| Provider | **Groq** (free tier available; OpenAI-compatible chat API, official `groq` Python SDK) |
| Text model | **`openai/gpt-oss-120b`** (OpenAI's open-weight model), JSON mode, temperature 0 |
| Vision model (scans only) | **`meta-llama/llama-4-scout-17b-16e-instruct`**. GPT-OSS cannot see images, so a scan is transcribed first, then extracted. |
| Override | `SKB_GROQ_MODEL`, `SKB_GROQ_VISION_MODEL` environment variables, since hosted model line-ups change |
| Per scheme | About 6k input and 3–4k output tokens, so **about $0.003–0.005 per scheme** at Groq's paid on-demand rates (about $0.15 / $0.60 per million tokens for GPT-OSS-120B; check groq.com/pricing). **$0 on the free tier.** |
| 5,000 schemes | About **$15–25** at paid rates. The free tier has per-minute and per-day limits, so it suits testing; the full back-fill would use a paid key or be spread over days. |
| MyScheme listings | No AI cost. They are already structured, so a deterministic mapper reads them. |

Each `--mode llm` run records real token counts and the cost at paid rates in `out/run_llm.json`.

**Where I'd spend more, and less:** scans and multi-page circulars get the vision step plus the larger model. Clean text pages could try `openai/gpt-oss-20b`, but only if it passes the same readiness gate.

> ⚠ **Not yet run against the live Groq API**, because I had no key while building. The full Groq code path (scan transcription, JSON retry, mapping, hallucination check) is tested with a fake Groq client in `tests/test_edge_cases.py`. The first thing I'd do with a key is run `--mode llm` and compare its Accuracy tab with the offline numbers.

## 7. Decisions and what I decided against

| Decision | Alternative I rejected | Why |
|---|---|---|
| **Code checks every quote** against the source text | Trusting the model's citations, or asking it for a confidence score | Models can cite fluently and wrongly. A string match costs nothing and can't be talked around. |
| **Conflicts are never auto-resolved**, only annotated with dates ("newest source is…") | "Official document always wins", or "newest wins" | The PDF can itself be outdated (see §10). The person with field knowledge makes the call, and the hint makes it a 5-second call. |
| **Scanned official doc unreadable → high-stakes fields left empty**, not filled from MyScheme | Showing the MyScheme value with low confidence | That was my first version. The evaluator marked it dangerous: a low-confidence number still looks like an answer. |
| **Send the model numbered lines**, not the raw PDF | Uploading the PDF file | The model then quotes exactly the text we hold, so the quote check is exact, and the model can cite "page 2, line 7". |
| **Vision model transcribes scans, then the text model extracts** | One vision model doing everything | GPT-OSS is strong at structured extraction but text-only; splitting also gives a transcription that the reviewer can compare with the image. |
| **Documents must match exactly**; other lists only mostly | The same fuzzy rule for all lists | A missing document gets an application rejected at the office. Slightly different wording in an eligibility line doesn't. |
| **An offline baseline as well as the LLM** | LLM only | It lets anyone run and test the whole pipeline without a key, and gives the LLM something to beat. |

## 8. Assumptions

- **Documents have recognisable sections** (benefit, eligibility, documents, and so on), as most notifications, GRs and scheme pages do. The offline extractor depends on this; the LLM does not.
- **The official department document outranks MyScheme**, but only as a hint, because the department may not have updated its own page either.
- **A source older than 12 months is suspect.** It gets a freshness warning, not an automatic downgrade.
- **One document describes one scheme.** Multi-scheme circulars are out of scope here (that's A2).
- **Values stay in the source language.** Translation for the agent app is a separate, reviewable step.
- **Amounts are a single rupee figure.** Category-dependent amounts need a richer field; the reviewer sees the full sentence in the quote.
- **Monthly volume is small at first.** The free Groq tier is fine for a pilot; the 5,000-scheme back-fill needs paid limits (about $15–25 total).

## 9. Where this falls short, and how someone would notice

| Gap | How you'd notice |
|---|---|
| Groq path not yet run live | There is no `out/run_llm.json` or `eval_llm.md` |
| On scans, quotes are checked against the vision model's *transcription*, so a misread digit (₹1,200 read as ₹1,280) could pass. Confidence is capped at 0.6 and the note says so. | The Accuracy tab's "Scanned PDF" row, and reviewer corrections on scans, run higher than for text PDFs |
| Marathi/Hindi OCR quality of the vision model is unknown | Same row; fix by adding an independent OCR cross-check |
| The offline rules are tuned to 4 synthetic documents | Accuracy drops sharply on any new real document, which is why the gate needs held-out real data |
| Lists in different languages (Marathi eligibility vs English MyScheme eligibility) don't match except for documents, which have a canonical code list | False conflicts on multilingual schemes; safe but costs reviewer time |
| Amounts that vary by category or come in instalments are reduced to one number | Reviewers correct these often; the exported corrections show it per field |

## 10. "A senior researcher says the AI got a benefit amount wrong. I check, and the AI's value matches the PDF. What do I do next?"

I'd treat it as information, not a dispute. Matching the PDF only shows that the extraction worked, not that the value is right.

1. **Ask what they expected and why.** Usually there's a reason: a newer GR or corrigendum, a state top-up on a central scheme, a category-specific amount, or what applicants are actually receiving in the field.
2. **Look for that source.** If it exists, add it to the manifest. The field then becomes a *conflict*, with both values and both quotes, and the researcher's knowledge is now recorded with evidence.
3. **Classify the error correctly.** This is a *source* error (stale or incomplete document), not an *extraction* error. The two need different fixes: better extraction vs better source coverage and freshness alerts. The freshness warning in this project is the start of the second.
4. **Add the case to the answer key** (`import-decisions`), labelled "PDF outdated", so we can measure how often it happens.
5. **If the PDF turns out to be right,** I'd show the quote and the page and settle it together, without ever framing it as "the AI was right". Their willingness to challenge drafts is exactly what keeps wrong values away from citizens.

## 11. Deliberately left out

- **OCR in offline mode** (Tesseract needs a system install). With more time I'd add independent OCR to cross-check the vision model's transcription of scans.
- **Multi-scheme circulars, monitoring at scale and drift alerts** (problem A2).
- **A real database, user accounts, versioning and publishing.** The console keeps decisions in the browser and exports JSON; production would store them with reviewer ID and timestamp.
- **Fetching live MyScheme or department pages.** Out of scope, and the brief asks not to use real URLs.

## 12. How I used AI tools

I built this with **Claude Code** (Anthropic's coding assistant) as a pair programmer. It helped generate the synthetic documents (including rendering the Marathi scan), write first drafts of the modules and the review console, and run the tests. I chose the problem, the evidence/conflict/unreadable-source rules, the evaluation categories and readiness thresholds, the switch to Groq's free models, and the trade-offs in §7. I reviewed and can explain or change every part of the code. One change came from reading the evaluation output: the dangerous-error fix described in §3.

## Project layout

```
skb/
  schema.py        field record format (brief's table) + source manifest
  loaders.py       PDF / scanned PDF / HTML / text / MyScheme → located lines
  normalize.py     ₹ amounts (lakh grouping, Devanagari digits), frequencies, Hindi/Marathi dates
  extract_rules.py offline bilingual section-based extractor (default)
  extract_llm.py   Groq extractor: GPT-OSS-120B for text, Llama 4 Scout vision for scans
  verify.py        quote-must-exist grounding check
  compare.py       when two values mean the same (shared by reconciler and evaluator)
  reconcile.py     found / conflict / not_found across sources
  pipeline.py      runs everything; freshness warnings; run metadata and cost
  evaluate.py      field-level scoring, conflict recall, grounding rate, by doc type, readiness gate
  feedback.py      reviewer decisions → answer key (import-decisions)
  review.py        builds out/review.html (Review · Accuracy · How it works; light/dark)
  samples.py       regenerates the two sample PDFs
data/
  sources/         the 4 synthetic official documents (+ PNG preview of the scan)
  myscheme/        synthetic MyScheme listing snapshots
  manifest.json    which source belongs to which scheme, authority, dates, placeholder links
  gold.json        hand-checked answers
out/               generated records, run metadata, review console, evaluation reports
tests/             15 edge-case tests (incl. the Groq path with a fake client)
```
