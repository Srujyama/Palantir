"""Provenance / audit export.

The thesis of the Bottleneck Radar is "verifiable, not a black box". This
module makes that claim *checkable at runtime*: for every signal the pipeline
surfaces (primary bottleneck, secondary bottlenecks, every silent failure) it
re-derives the chain of custody from the stored triage payload back to the
source note:

    signal -> recommended action -> guideline citation -> evidence span(s)

and, for every evidence span, it re-verifies the auditability invariant
against the patient's own note:

    note_text[start:end] == span.text   ->   verified == True

Nothing here re-runs the classifier or calls an LLM. It reads the materialized
triage payload (the same JSON the UI renders) and the immutable note, and
proves the two line up. If a span fails to verify that is a *real* defect in
the extraction/classification path, not a tolerable rounding error — the
export surfaces it (verified == False) rather than hiding it, so the corpus
summary's pct_verified is an honest health metric.

Read-only by construction: every function takes a Session and only queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.orm import Patient, Triage


# ---------------------------------------------------------------------------
# Dataclasses (serialized by the API layer)
# ---------------------------------------------------------------------------

@dataclass
class VerifiedSpan:
    start: int
    end: int
    text: str
    # verified == (note_text[start:end] == text). The whole point of the
    # export: a False here is a loud, traceable bug, never silently dropped.
    verified: bool

    def to_dict(self) -> Dict:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "verified": self.verified,
        }


@dataclass
class AuditSignal:
    # Where this signal came from in the payload: "primary", "secondary",
    # or "silent_failure". Lets a reviewer see the provenance shape at a glance.
    source: str
    # A short human signal string ("Medication safety risk", a missing protocol
    # action, ...) — what the floor actually sees.
    signal: str
    category: str
    urgency: str
    owner: str
    recommended_action: str
    citation: Optional[str]
    evidence_spans: List[VerifiedSpan] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "source": self.source,
            "signal": self.signal,
            "category": self.category,
            "urgency": self.urgency,
            "owner": self.owner,
            "recommended_action": self.recommended_action,
            "citation": self.citation,
            "evidence_spans": [s.to_dict() for s in self.evidence_spans],
        }


@dataclass
class PatientAudit:
    patient_id: str
    note_text: str
    signals: List[AuditSignal]

    # Per-patient roll-up of the same numbers the corpus summary aggregates.
    n_signals: int
    n_with_citation: int
    n_evidence_spans: int
    n_verified_spans: int

    def to_dict(self) -> Dict:
        return {
            "patient_id": self.patient_id,
            "note_text": self.note_text,
            "signals": [s.to_dict() for s in self.signals],
            "n_signals": self.n_signals,
            "n_with_citation": self.n_with_citation,
            "n_evidence_spans": self.n_evidence_spans,
            "n_verified_spans": self.n_verified_spans,
            "pct_verified": _pct(self.n_verified_spans, self.n_evidence_spans),
            "pct_cited": _pct(self.n_with_citation, self.n_signals),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(numerator: int, denominator: int) -> float:
    """Percent, rounded to two places. Zero denominator -> 100.0.

    An audit with no spans/signals is vacuously fully verified/cited; that
    keeps a genuinely clear patient (no bottleneck, no evidence) from dragging
    a corpus metric to 0 and is the mathematically defensible convention.
    """
    if denominator == 0:
        return 100.0
    return round(100.0 * numerator / denominator, 2)


def _verify_span(note_text: str, span: Dict) -> VerifiedSpan:
    """Re-check note_text[start:end] == text. This is THE auditability
    invariant; an honest export reports the truth value, it does not assert it.
    """
    start = span.get("start", -1)
    end = span.get("end", -1)
    text = span.get("text", "")
    verified = (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start <= end <= len(note_text)
        and note_text[start:end] == text
    )
    return VerifiedSpan(start=start, end=end, text=text, verified=verified)


def _bottleneck_signal(note_text: str, source: str, b: Dict) -> Optional[AuditSignal]:
    """Build an AuditSignal from a (primary|secondary) bottleneck payload dict.

    The synthetic "clear" bottleneck (no category gap, no evidence, no
    citation) is not a recommendation that needs tracing, so it is skipped:
    auditing "no action required" against a guideline would be meaningless.
    """
    if b.get("category") == "clear":
        return None
    spans = [_verify_span(note_text, s) for s in b.get("evidence", [])]
    return AuditSignal(
        source=source,
        signal=b.get("label", b.get("category", "")),
        category=b.get("category", ""),
        urgency=b.get("urgency", ""),
        owner=b.get("owner", ""),
        recommended_action=b.get("recommended_action", ""),
        citation=b.get("citation"),
        evidence_spans=spans,
    )


def _silent_failure_signal(note_text: str, sf: Dict) -> AuditSignal:
    """Build an AuditSignal from a silent_failure payload dict.

    A silent failure carries a single trigger_evidence span (what fired the
    protocol). Its citation is the protocol's guideline and is always present,
    which is exactly the provenance guarantee we want to demonstrate.
    """
    trig = sf.get("trigger_evidence")
    spans = [_verify_span(note_text, trig)] if isinstance(trig, dict) else []
    return AuditSignal(
        source="silent_failure",
        signal=sf.get("missing_action", ""),
        category="missing_soc",
        urgency=sf.get("urgency", ""),
        owner=sf.get("owner", ""),
        recommended_action=sf.get("missing_action", ""),
        citation=sf.get("citation"),
        evidence_spans=spans,
    )


def _signals_for_payload(note_text: str, payload: Dict) -> List[AuditSignal]:
    """Flatten a stored triage payload into the ordered list of audit signals.

    Order: primary, then secondary (in payload order), then every silent
    failure. This is the same order a reviewer reads the patient card.
    """
    signals: List[AuditSignal] = []

    primary = payload.get("primary")
    if isinstance(primary, dict):
        sig = _bottleneck_signal(note_text, "primary", primary)
        if sig is not None:
            signals.append(sig)

    for b in payload.get("secondary", []):
        if isinstance(b, dict):
            sig = _bottleneck_signal(note_text, "secondary", b)
            if sig is not None:
                signals.append(sig)

    for sf in payload.get("silent_failures", []):
        if isinstance(sf, dict):
            signals.append(_silent_failure_signal(note_text, sf))

    return signals


def _roll_up(signals: List[AuditSignal]) -> Dict[str, int]:
    n_signals = len(signals)
    n_with_citation = sum(1 for s in signals if s.citation)
    n_evidence_spans = sum(len(s.evidence_spans) for s in signals)
    n_verified_spans = sum(
        1 for s in signals for sp in s.evidence_spans if sp.verified
    )
    return {
        "n_signals": n_signals,
        "n_with_citation": n_with_citation,
        "n_evidence_spans": n_evidence_spans,
        "n_verified_spans": n_verified_spans,
    }


# ---------------------------------------------------------------------------
# Public API (read-only over the live DB)
# ---------------------------------------------------------------------------

def build_patient_audit(db: Session, patient_id: str) -> Optional[PatientAudit]:
    """Provenance export for one patient, or None if the patient is unknown.

    Reads the materialized triage payload + the immutable note and re-verifies
    every evidence span. Does not re-run the classifier.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).one_or_none()
    if patient is None:
        return None

    triage: Optional[Triage] = patient.triage
    note_text = patient.note_text or ""
    payload = triage.payload if triage and triage.payload else {}

    signals = _signals_for_payload(note_text, payload)
    roll = _roll_up(signals)

    return PatientAudit(
        patient_id=patient.id,
        note_text=note_text,
        signals=signals,
        n_signals=roll["n_signals"],
        n_with_citation=roll["n_with_citation"],
        n_evidence_spans=roll["n_evidence_spans"],
        n_verified_spans=roll["n_verified_spans"],
    )


def build_corpus_summary(db: Session) -> Dict:
    """Corpus-wide provenance health metrics.

    Aggregates the per-patient roll-up across every patient with a triage row:
    how many signals exist, how many carry a citation, how many evidence spans
    exist, and how many re-verify against their note. pct_verified is the
    headline number that proves the auditability guarantee at corpus scale.
    """
    patients = db.query(Patient).all()

    n_patients = 0
    n_signals = 0
    n_with_citation = 0
    n_evidence_spans = 0
    n_verified_spans = 0
    unverified_spans: List[Dict] = []

    for p in patients:
        triage: Optional[Triage] = p.triage
        if triage is None or not triage.payload:
            continue
        n_patients += 1
        note_text = p.note_text or ""
        signals = _signals_for_payload(note_text, triage.payload)
        for s in signals:
            n_signals += 1
            if s.citation:
                n_with_citation += 1
            for sp in s.evidence_spans:
                n_evidence_spans += 1
                if sp.verified:
                    n_verified_spans += 1
                else:
                    # Surface offenders loudly so a real bug is traceable to
                    # the exact patient + span rather than buried in a ratio.
                    unverified_spans.append(
                        {
                            "patient_id": p.id,
                            "source": s.source,
                            "category": s.category,
                            "span": sp.to_dict(),
                        }
                    )

    return {
        "n_patients": n_patients,
        "n_signals": n_signals,
        "n_with_citation": n_with_citation,
        "pct_cited": _pct(n_with_citation, n_signals),
        "n_evidence_spans": n_evidence_spans,
        "n_verified_spans": n_verified_spans,
        "pct_verified": _pct(n_verified_spans, n_evidence_spans),
        # Empty in a healthy corpus; non-empty == a real, located defect.
        "unverified_spans": unverified_spans,
    }
