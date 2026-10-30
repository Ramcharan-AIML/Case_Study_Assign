"""The field record format from the brief, plus the source manifest."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

FIELDS = [
    "scheme_name",
    "department",
    "benefit_type",
    "benefit_amount",
    "benefit_frequency",
    "eligibility",
    "documents_required",
    "how_to_apply",
    "deadline",
    "official_link",
]
LIST_FIELDS = {"eligibility", "documents_required", "how_to_apply"}
# Fields where a wrong value directly changes what a citizen gets or does.
HIGH_STAKES = {"benefit_amount", "benefit_frequency", "deadline", "documents_required", "eligibility"}

Status = Literal["found", "not_found", "conflict"]


class Source(BaseModel):
    source_ref: str
    scheme_ref: str
    path: str
    kind: Literal["pdf", "html", "text", "myscheme"]
    authority: Literal["primary", "secondary"]
    language: str
    title: str
    published_on: str
    captured_at: str
    link: str  # placeholder reference; never a real URL for synthetic data


class Evidence(BaseModel):
    quote: str  # exact text from the source
    location: str  # page / section / line
    source_ref: str
    source_link: str
    captured_at: str


class Candidate(BaseModel):
    """One value proposed by one source. A conflict keeps several of these."""

    value: Any
    evidence: list[Evidence]
    confidence: float
    source_ref: str
    authority: str
    note: str | None = None


class FieldRecord(BaseModel):
    scheme_ref: str
    field: str
    value: Any = None  # None when not_found or conflict (see candidates)
    evidence: list[Evidence] = []
    confidence: float = 0.0
    status: Status
    note: str | None = None
    candidates: list[Candidate] = []  # filled only for conflicts
    extractor: str = "rules"
