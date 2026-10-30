"""Each test is one of the tricky real-world cases the pipeline must survive."""
from pathlib import Path

from skb import normalize as nz
from skb.compare import values_equal
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


# --- Groq LLM path, with a fake Groq client (no API key, no network) ----------

class _FakeGroq:
    """Mimics groq.Groq().chat.completions.create and records what was sent."""

    def __init__(self, replies):
        self.replies, self.sent = list(replies), []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        from types import SimpleNamespace as NS
        self.sent.append(kwargs)
        return NS(choices=[NS(message=NS(content=self.replies.pop(0)))], usage=NS(prompt_tokens=1000, completion_tokens=200))


def _fields(**overrides):
    import json
    from skb.schema import FIELDS
    empty = {"value": None, "quotes": [], "location": None, "note": "not stated"}
    return json.dumps({"fields": {f: overrides.get(f, empty) for f in FIELDS}})


def test_llm_invented_quote_is_dropped_by_grounding_check():
    from skb import extract_llm, verify

    doc = load(SOURCES["SRC-001-A"], DATA)
    reply = _fields(
        benefit_amount={"value": "Rs. 2,000", "quotes": ["Monthly pension of Rs. 2,000 per month"],  # invented
                        "location": "page 1, line 9", "note": None},
        deadline={"value": "30 June 2026", "location": "page 2, line 10", "note": None,
                  "quotes": ["6. Last Date: Applications for the year 2026-27 must be submitted by 30 June 2026."]})
    results, text, usage = extract_llm.extract(doc, _FakeGroq([reply]))
    checked = verify.apply(results, text)
    assert checked["benefit_amount"][0] is None and "grounding check" in checked["benefit_amount"][1]
    assert checked["deadline"][0].value == "2026-06-30"
    assert usage[0]["model"] == extract_llm.TEXT_MODEL


def test_llm_bad_json_is_retried_once():
    from skb import extract_llm

    doc = load(SOURCES["SRC-004-A"], DATA)
    fake = _FakeGroq(["not json at all", _fields()])
    extract_llm.extract(doc, fake)
    assert len(fake.sent) == 2 and "invalid" in fake.sent[1]["messages"][-1]["content"]


def test_llm_scan_goes_through_vision_model_then_text_model():
    from skb import extract_llm

    doc = load(SOURCES["SRC-003-A"], DATA)
    transcription = "लाभ: पात्र लाभार्थीस दरमहा ₹ १,२०० अर्थसहाय्य थेट बँक खात्यात जमा केले जाईल."
    reply = _fields(benefit_amount={"value": "₹ १,२००", "quotes": [transcription], "location": "scan page 1, line 1", "note": None})
    fake = _FakeGroq([transcription, reply])
    results, text, _ = extract_llm.extract(doc, fake)
    assert fake.sent[0]["model"] == extract_llm.VISION_MODEL and fake.sent[1]["model"] == extract_llm.TEXT_MODEL
    cand = results["benefit_amount"][0]
    assert cand.value == 1200 and cand.confidence == extract_llm.SCANNED_CONF_CAP


# --- Feedback loop and readiness gate ----------------------------------------

def test_reviewer_corrections_become_test_answers():
    from skb.feedback import to_gold_entry

    entry = to_gold_entry({"scheme_ref": "SCH004", "field": "documents_required", "decision": "corrected",
                           "value": "MCP card; Aadhaar card; bank passbook; ration card"}, None)
    assert entry["status"] == "found" and len(entry["value"]) == 4 and entry["origin"] == "reviewer"


def test_readiness_gate_fails_on_a_tiny_test_set():
    from skb.evaluate import readiness

    result = {"n_schemes": 4, "high_stakes_dangerous_rate": 0.0, "grounding_rate": 1.0, "conflict_recall": 1.0, "accuracy": 0.9}
    gate = readiness(result)
    assert not gate["ready"] and [c["passed"] for c in gate["checks"]] == [False, True, True, True, True]
