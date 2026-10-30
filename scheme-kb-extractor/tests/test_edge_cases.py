"""Each test is one of the tricky real-world cases the pipeline must survive."""
from pathlib import Path

from skb import normalize as nz
from skb.compare import values_equal
from skb.extract_llm import to_candidates
from skb.loaders import load
from skb.pipeline import load_manifest, run
from skb.reconcile import reconcile
from skb.schema import Candidate, Evidence

DATA = Path(__file__).resolve().parent.parent / "data"
SOURCES = {s.source_ref: s for s in load_manifest(DATA)}


def _ev(q="x"):
    return Evidence(quote=q, location="l", source_ref="S", source_link="synthetic://s", captured_at="2026-10-28")


# --- Numbers and dates in Indian formats -------------------------------------

def test_revised_amount_ignores_the_earlier_figure():
    text = "Rs. 1,500 per month. This revises the earlier assistance of Rs. 1,000 per month."
    value, amounts = nz.benefit_amount(text)
    assert value == 1500
    assert any(a.value == 1000 and a.skipped_reason for a in amounts)


def test_devanagari_digits_and_lakh_grouping():
    assert nz.benefit_amount("₹ १०,००० की एकमुश्त राशि")[0] == 10000
    assert nz.benefit_amount("सहायता ₹ 1,20,000")[0] == 120000


def test_income_ceiling_is_not_a_benefit():
    assert nz.benefit_amount("Annual family income not exceeding Rs. 1,20,000.")[0] is None


def test_marathi_and_hindi_dates():
    assert nz.find_dates("अंतिम दिनांक: ३१ डिसेंबर २०२६") == ["2026-12-31"]
    assert nz.find_dates("अंतिम तिथि 15 मार्च 2027") == ["2027-03-15"]
    assert nz.find_dates("Applications for the year 2026-27 must be submitted by 30 June 2026.") == ["2026-06-30"]


def test_rolling_and_relative_deadlines():
    assert nz.ROLLING_RE.search("इस योजना के लिए आवेदन पूरे वर्ष खुले रहते हैं।")
    assert nz.relative_deadline("Applications must be made within 270 days of delivery.") == "Within 270 days of delivery"


def test_documents_match_across_languages():
    assert values_equal("documents_required", ["आधार कार्ड", "बँक पासबुक"], ["Aadhaar card", "Bank passbook (first page)"])
    assert not values_equal("documents_required", ["Aadhaar card", "Domicile certificate"], ["Aadhaar card"])


# --- Sources and conflicts ---------------------------------------------------

def test_scanned_pdf_is_detected_not_guessed():
    doc = load(SOURCES["SRC-003-A"], DATA)
    assert doc.needs_ocr and doc.lines == []


def test_disagreeing_sources_become_conflict_with_both_values():
    a = (SOURCES["SRC-001-A"], Candidate(value=1500, evidence=[_ev()], confidence=0.9, source_ref="SRC-001-A", authority="primary"), None)
    m = (SOURCES["SRC-001-M"], Candidate(value=1000, evidence=[_ev()], confidence=0.9, source_ref="SRC-001-M", authority="secondary"), None)
    rec = reconcile("SCH001", "benefit_amount", [a, m], "rules")
    assert rec.status == "conflict" and rec.value is None
    assert sorted(c.value for c in rec.candidates) == [1000, 1500]


def test_stale_myscheme_value_not_prefilled_when_official_doc_unreadable():
    m = (SOURCES["SRC-003-M"], Candidate(value=1000, evidence=[_ev()], confidence=0.9, source_ref="SRC-003-M", authority="secondary"), None)
    scan = (SOURCES["SRC-003-A"], None, "scanned")
    rec = reconcile("SCH003", "benefit_amount", [scan, m], "rules", primary_unreadable=True)
    assert rec.status == "not_found" and rec.value is None and rec.candidates[0].value == 1000


def test_end_to_end_offline_run_has_no_dangerous_errors():
    from skb.evaluate import evaluate
    import json, tempfile

    with tempfile.TemporaryDirectory() as tmp:
        records = run(DATA, Path(tmp), "rules")
    payload = {k: [r.model_dump() for r in v] for k, v in records.items()}
    result = evaluate(payload, json.loads((DATA / "gold.json").read_text(encoding="utf-8")))
    assert result["dangerous_error_rate"] == 0


# --- LLM path: hallucination guard (no API call; fake model output) ----------

def test_llm_invented_quote_is_dropped_by_grounding_check():
    from skb import verify

    doc = load(SOURCES["SRC-001-A"], DATA)
    empty = {"value": None, "quotes": [], "location": None, "note": "not stated"}
    raw = {"transcription": None, "fields": {f: dict(empty) for f in
           ["scheme_name", "department", "benefit_type", "benefit_amount", "benefit_frequency",
            "eligibility", "documents_required", "how_to_apply", "deadline", "official_link"]}}
    raw["fields"]["benefit_amount"] = {"value": "Rs. 2,000", "quotes": ["Monthly pension of Rs. 2,000 per month"],
                                       "location": "page 1", "note": None}  # invented
    raw["fields"]["deadline"] = {"value": "30 June 2026", "location": "page 2", "note": None,
                                 "quotes": ["Applications for the year 2026-27 must be submitted by 30 June 2026."]}
    results, text = to_candidates(doc, raw)
    checked = verify.apply(results, text)
    assert checked["benefit_amount"][0] is None and "grounding check" in checked["benefit_amount"][1]
    assert checked["deadline"][0].value == "2026-06-30"
