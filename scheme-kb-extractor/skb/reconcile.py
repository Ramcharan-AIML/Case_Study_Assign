"""Merges per-source candidates into one FieldRecord per field.

Rules:
- Sources agree        -> found; evidence from every source; confidence nudged up.
- Only MyScheme speaks -> found, but confidence capped at 0.5 and flagged.
- Sources disagree     -> conflict; every value kept with its own evidence.
                          Never auto-resolved. The note gives the reviewer
                          the publication dates so they can decide quickly.
"""
from __future__ import annotations

from .compare import values_equal
from .schema import HIGH_STAKES, Candidate, FieldRecord, Source

PerSource = list[tuple[Source, Candidate | None, str | None]]


def _rank(c: Candidate) -> tuple:
    return (c.authority != "primary", -c.confidence)


def reconcile(scheme_ref: str, field: str, results: PerSource, extractor: str,
              primary_unreadable: bool = False) -> FieldRecord:
    by_ref = {s.source_ref: s for s, _, _ in results}
    found = [c for _, c, _ in results if c is not None]

    if not found:
        note = " | ".join(f"[{s.source_ref}] {r}" for s, _, r in results)
        return FieldRecord(scheme_ref=scheme_ref, field=field, status="not_found", note=note, extractor=extractor)

    groups: list[list[Candidate]] = []
    for c in found:
        for g in groups:
            if values_equal(field, g[0].value, c.value):
                g.append(c)
                break
        else:
            groups.append([c])

    silent = [f"[{s.source_ref}] silent: {r}" for s, c, r in results if c is None]

    if len(groups) == 1:
        g = sorted(groups[0], key=_rank)
        conf = min(0.98, max(c.confidence for c in g) + 0.05 * (len(g) - 1))
        notes = [f"[{c.source_ref}] {c.note}" for c in g if c.note]
        if all(c.authority == "secondary" for c in g) and primary_unreadable and field in HIGH_STAKES:
            # The official document exists but we could not read it. MyScheme may be stale
            # (it often is), so a high-stakes value is NOT pre-filled: shown as a hint only.
            return FieldRecord(scheme_ref=scheme_ref, field=field, status="not_found", candidates=g[:1],
                               note=(f"Official document could not be read, so this is left empty. MyScheme says "
                                     f"{g[0].value!r} — unverified hint only; check the official document. ")
                                    + " ".join(silent), extractor=extractor)
        if all(c.authority == "secondary" for c in g):
            conf = min(conf, 0.5)
            notes.insert(0, "Only the MyScheme listing states this; the official source is silent or unreadable. "
                            "Verify against an official document before approving.")
        elif len(g) > 1:
            notes.append(f"Corroborated by {len(g)} sources.")
        notes += silent
        return FieldRecord(scheme_ref=scheme_ref, field=field, value=g[0].value,
                           evidence=[e for c in g for e in c.evidence], confidence=round(conf, 2),
                           status="found", note=" ".join(notes) or None, extractor=extractor)

    candidates = []
    for g in groups:
        g = sorted(g, key=_rank)
        candidates.append(Candidate(value=g[0].value, evidence=[e for c in g for e in c.evidence],
                                    confidence=g[0].confidence, source_ref=", ".join(c.source_ref for c in g),
                                    authority=g[0].authority, note=g[0].note))
    described = [
        f"{c.value!r} from {c.source_ref} ({by_ref[c.source_ref.split(', ')[0]].authority}, "
        f"published {by_ref[c.source_ref.split(', ')[0]].published_on})"
        for c in candidates
    ]
    newest = max(candidates, key=lambda c: by_ref[c.source_ref.split(", ")[0]].published_on)
    note = ("Sources disagree; not auto-resolved. " + " vs ".join(described) +
            f". Reviewer hint: the most recently published source is {newest.source_ref}.")
    return FieldRecord(scheme_ref=scheme_ref, field=field, status="conflict", candidates=candidates,
                       evidence=[e for c in candidates for e in c.evidence], confidence=0.3,
                       note=note, extractor=extractor)
