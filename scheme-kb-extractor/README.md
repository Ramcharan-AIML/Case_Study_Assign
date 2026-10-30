# Scheme field extraction with evidence (Case study A1)

AI prepares a **first draft** of a scheme record from government documents. Every value carries the exact
quote, the page or section and the source it came from. When sources disagree, the draft keeps both values
and does not pick one. A researcher checks every field on a review screen before anything is published.

```bash
pip install -r requirements.txt
python -m skb all                 # offline: extract -> review screen -> accuracy report (no API key needed)
python -m pytest -q               # 11 edge-case tests
# then open out/review.html in a browser
```

With an Anthropic API key, `python -m skb all --mode llm` runs the Claude extractor on the same documents
(see [Model and cost](#model-and-cost)).

---

## 1. How it works

```
 official PDF / scanned PDF / web page / press note        MyScheme listing
                 │                                                │
           loaders.py  ── every line keeps its page / section ────┘
                 │
     ┌───────────┴────────────┐
 extract_rules.py        extract_llm.py (Claude)
 (offline baseline)      reads text PDFs, scans, Hindi, Marathi
     └───────────┬────────────┘
           verify.py   ── a value survives only if its quote is literally in the source
                 │
          reconcile.py ── agree → found · disagree → CONFLICT (both kept) · official doc unreadable → empty
                 │
   out/records_*.json  ──►  out/review.html (researcher approves / corrects / resolves)
                 │                      │ exported decisions
           evaluate.py  ◄── data/gold.json (hand-checked answers; grows from reviewer decisions)
```

Three rules are built into the code, not left to the model:

1. **No quote, no value.** `verify.py` drops any value whose quote cannot be found in the source text, and records why.
2. **Never pick a side silently.** Disagreeing sources produce `status: "conflict"`, with every value and its own evidence kept. The note gives publication dates so the reviewer can decide quickly.
3. **Never present a guess.** A scanned document that cannot be read gives "not found, here's why". It never falls back to a plausible value.

## 2. Sample documents and the tricky case each one tests

All synthetic. "Vindhyachal" is a fictional state. Links use the reserved `.example` domain or `synthetic://` placeholders.

| Scheme | Sources | What it tests |
|---|---|---|
| **SCH001** Old-age pension | English 2-page text **PDF** + **MyScheme** listing | **Conflict.** The notification revised the pension from ₹1,000 to ₹1,500, but MyScheme still shows ₹1,000 and last year's deadline, and it omits one required document. The same PDF mentions the *earlier* ₹1,000 and an *income ceiling* of ₹1,20,000; neither should be taken as the benefit. Fields are spread across two pages. |
| **SCH002** Girl-child education incentive | **Hindi** department **web page** | Devanagari digits (₹ १०,०००), "एकमुश्त" (one-time), **no fixed deadline** ("आवेदन पूरे वर्ष खुले रहते हैं"), and **no official link**. The link must stay empty; the page's own address is not assumed to be one. |
| **SCH003** Widow assistance | **Scanned Marathi PDF** (image only, no text layer, tilted, noisy) + partial MyScheme | **Unreadable official source.** MyScheme shows an outdated ₹1,000 against ₹1,200 in the circular. The name appears in two scripts. |
| **SCH004** Maternal nutrition | English **press note** + MyScheme | **Vague source.** The amount is "as per the norms prescribed", so the document gives no figure; only MyScheme gives ₹5,000. There's a **relative deadline** ("within 270 days of delivery"), no "Scheme name:" label (the name comes from the headline), and a cash + in-kind benefit. |

You can view the scan at `data/sources/SCH003_widow_assistance_scan_mr.png`.

## 3. Results

`python -m skb all` gives this report (full version in `out/eval_rules.md`):

| Measure (offline extractor, 40 fields) | Value |
|---|---|
| Field-level accuracy | **85%** |
| Dangerous error rate (wrong value that looks fine) | **0%** |
| Safe error rate (left empty, so the reviewer fills it in) | 15% |

**How to read this honestly:**
- All 6 misses are in **SCH003, the scanned Marathi circular**. The offline extractor has no OCR, so it correctly refuses to read the scan. That is the expected outcome, not a bug. The Claude extractor reads scans and is the production path.
- On the three text documents the offline extractor is 100% correct, including all three SCH001 conflicts. **This does not show that the extractor is good.** I wrote both the documents and the rules, so this only shows that the pipeline (evidence, verification, conflicts, review, scoring) works end to end. A real accuracy number has to come from documents the extractor has never seen (see §5).
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
                   "location": "page 1, line 9", "source_ref": "SRC-001-A",
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

The two numbers to manage are **accuracy**, which measures time saved, and the **dangerous error rate**, which measures harm. They are scored per field because a wrong scheme name is an annoyance, while a wrong amount or deadline costs a family money. The evaluator reports *high-stakes* fields (amount, frequency, deadline, documents, eligibility) separately.

**Proposed go/no-go before running on 5,000 schemes:**

1. **Build a test set from real work.** Take about 100 schemes researchers have already entered by hand, stratified by document type (text PDF, scan, web page, Hindi, Marathi and other languages, multi-scheme circulars) and by central vs state. Their existing entries, re-checked, become `gold.json`. Hold out about 30 that nobody tunes prompts on.
2. **Thresholds** on the held-out set, per document type and not just overall:
   - Dangerous error rate on high-stakes fields **≤ 1%**, with no single field type above 2%.
   - 100% of non-empty values pass the quote check (enforced by code, so this is a regression test).
   - Conflict recall **≥ 95%**: of the planted or known disagreements, how many are surfaced.
   - Accuracy **≥ 80%** overall. Below that, checking is not faster than typing.
3. **Time it.** Five researchers each do 10 schemes from scratch and 10 from the draft. If checking is not clearly faster (I'd want about 40% less time), the accuracy number doesn't matter.
4. **Roll out in stages:** 200 schemes, then 1,000, then the rest, re-scoring a 5% random sample of reviewed records at each stage. Reviewer corrections exported from the review screen go into `gold.json`, so the test set keeps growing with real failure cases.

## 6. Model and cost

| | |
|---|---|
| Model | **Claude Opus 5.5** (`claude-opus-5-5`), Anthropic API, structured JSON output, adaptive thinking at `effort: medium` |
| Price | $4 per million input tokens, $20 per million output tokens |
| Per scheme (estimate) | About 5–7k input tokens (instructions plus a 2–3 page document) and 2–4k output tokens, so **about $0.08–0.12 per scheme**. Scans cost a little more because the model also transcribes. |
| 5,000 schemes | About **$400–600** one-off, or about half that with the Batch API (50% discount, no rush needed for back-filling) |
| MyScheme listings | No AI cost. They are already structured, so a deterministic mapper reads them. |

These figures are **estimates**. The first `--mode llm` run writes the measured cost to `out/llm_usage.json`.
A cheaper model (Claude Haiku 5.5, about 40× cheaper) is worth testing against the same gold set, but only if it passes the same thresholds.

> ⚠ **Not yet run against the live API**, because I had no API key while building this. The code path is written against the SDK documentation, and its post-processing (mapping the response, the hallucination check) is unit-tested with a fake model response (`test_llm_invented_quote_is_dropped_by_grounding_check`). The first thing I'd do with a key is run it and compare its scores with the table above.

## 7. Decisions and what I decided against

| Decision | Alternative I rejected | Why |
|---|---|---|
| **Code checks every quote** against the source text | Trusting the model's citations, or asking it for a confidence score | Models can cite fluently and wrongly. A string match costs nothing and can't be talked around. |
| **Conflicts are never auto-resolved**, only annotated with dates ("newest source is…") | "Official document always wins", or "newest wins" | The PDF can itself be outdated (see §10). The person with field knowledge makes the call, and the hint makes it a 5-second call. |
| **Scanned official doc unreadable → high-stakes fields left empty**, not filled from MyScheme | Showing the MyScheme value with low confidence | That was my first version. The evaluator marked it dangerous: a low-confidence number still looks like an answer. |
| **Documents must match exactly**; other lists only mostly | The same fuzzy rule for all lists | A missing document gets an application rejected at the office. Slightly different wording in an eligibility line doesn't. |
| **An offline baseline as well as the LLM** | LLM only | It lets anyone run and test the whole pipeline without a key, and gives the LLM something to beat. |
| **One LLM call per document, structured output** | Separate calls per field, or a chain of agents | It's cheaper, and the model sees the whole document at once, which matters when the amount is on page 1 and the revision note on page 2. |

## 8. Assumptions

- **Documents have recognisable sections** (benefit, eligibility, documents, and so on), as most notifications, GRs and scheme pages do. The offline extractor depends on this; the LLM does not.
- **The official department document outranks MyScheme**, but only as a hint, because the department may not have updated its own page either.
- **One document describes one scheme.** Multi-scheme circulars are out of scope here (that's A2).
- **Values stay in the source language.** Translation for the agent app is a separate, reviewable step, not something extraction does silently.
- **Amounts are a single rupee figure.** Schemes with amounts that vary by category (e.g. more for SC/ST or by disability percentage) need a richer field. The current extractor takes the first current figure, and the reviewer would see the full sentence in the quote.
- **The capture date is when we fetched the source**, not when the department published it. Both are stored, because both matter for conflicts.

## 9. Where this falls short, and how someone would notice

| Gap | How you'd notice |
|---|---|
| Claude path not yet run live | `out/llm_usage.json` doesn't exist yet, and there is no `eval_llm.md` |
| On scans, the LLM's quotes are checked against *its own* transcription, so a misread digit (₹1,200 read as ₹1,280) could pass. Confidence is capped at 0.6 and the note says so. | Reviewer corrections on scanned documents run higher than on text PDFs. Track this per document type. |
| The offline rules are tuned to 4 synthetic documents | Accuracy drops sharply on any new real document, which is why the go/no-go is on held-out real data |
| Lists in different languages (Marathi eligibility vs English MyScheme eligibility) don't match except for documents, which have a canonical code list | False conflicts appear on multilingual schemes; they're safe but cost reviewer time |
| Scheme names in two scripts (निराधार… vs Niradhar…) would show as a conflict | Same: a false conflict |
| Amounts that vary by category or come in instalments are reduced to one number | Reviewers correct these often. The exported corrections show it per field. |

## 10. "A senior researcher says the AI got a benefit amount wrong. I check, and the AI's value matches the PDF. What do I do next?"

I'd treat it as information, not a dispute. Matching the PDF only shows that the extraction worked, not that the value is right.

1. **Ask what they expected and why.** Usually there's a reason: a newer GR or corrigendum, a state top-up on a central scheme, a category-specific amount, or what applicants are actually receiving in the field. They know things the document doesn't.
2. **Look for that source.** If it exists, add it to the manifest. The field then becomes a *conflict*, with both values and both quotes, and the researcher's knowledge is now recorded with evidence instead of living in their head.
3. **Classify the error correctly.** This is a *source* error (stale or incomplete document), not an *extraction* error. I'd track the two separately, because they need different fixes: better extraction vs better source coverage and freshness alerts.
4. **Add the case to the gold set,** labelled "PDF outdated", so we can measure how often it happens and add a rule such as "warn when a notification is older than X months, or when a newer circular from the same department exists".
5. **If the PDF turns out to be right,** I'd show the quote and the page and settle it together, without ever framing it as "the AI was right". Their willingness to challenge drafts is exactly what keeps wrong values away from citizens.

## 11. Deliberately left out

- **OCR in offline mode** (Tesseract needs a system install; the LLM reads scans anyway). With more time I'd add independent OCR purely to cross-check the LLM's transcription of scans, closing the gap described in §9.
- **Multi-scheme circulars, scale, cost controls and drift monitoring** (problem A2).
- **A real database, user accounts, versioning and publishing.** The review screen keeps decisions in the browser and exports JSON; production would write them to the knowledge base with reviewer ID and timestamp.
- **Fetching live MyScheme or department pages.** Out of scope, and the brief asks not to use real URLs.
- **Automatically importing exported review decisions into `gold.json`.** The formats line up; it's a small script.

## 12. How I used AI tools

I built this with **Claude Code** (Anthropic's coding assistant) as a pair programmer. It helped generate the synthetic documents (including rendering the Marathi scan), write first drafts of the modules and the review page, and run the tests. I decided which problem to tackle, the evidence/conflict/unreadable-source rules, the evaluation categories and thresholds, and the trade-offs in §7. I reviewed and can explain or change every part of the code. One change came from reading the evaluation output myself: the dangerous-error fix described in §3.

## Project layout

```
skb/
  schema.py        field record format (brief's table) + source manifest
  loaders.py       PDF / scanned PDF / HTML / text / MyScheme → located lines
  normalize.py     ₹ amounts (lakh grouping, Devanagari digits), frequencies, Hindi/Marathi dates
  extract_rules.py offline bilingual section-based extractor
  extract_llm.py   Claude extractor (structured output, vision for scans)
  verify.py        quote-must-exist grounding check
  compare.py       when two values mean the same (shared by reconciler and evaluator)
  reconcile.py     found / conflict / not_found across sources
  evaluate.py      field-level scoring against gold.json
  review.py        builds out/review.html
  samples.py       regenerates the two sample PDFs
data/
  sources/         the 4 synthetic official documents (+ PNG preview of the scan)
  myscheme/        synthetic MyScheme listing snapshots
  manifest.json    which source belongs to which scheme, authority, dates, placeholder links
  gold.json        hand-checked answers
out/               generated records, review screen, evaluation reports
tests/             11 edge-case tests
```
