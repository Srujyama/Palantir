"""Live triage sandbox.

Runs the full deterministic pipeline (extract -> classify -> ICD match) on
arbitrary pasted note text WITHOUT persisting anything. Returns a
stage-by-stage trace with per-stage timings so the demo UI can show exactly
what the rule engine saw and decided, with evidence offsets back into the
pasted text.

Also serves a curated set of sample notes drawn deterministically from the
real corpus (app/data/patient_notes.json) so the demo UI has one-click
examples covering every bottleneck category.

This is an operational coordination tool, NOT a clinical decision aid: every
signal traces to an evidence span and a cited protocol; no LLM calls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.nlp.extractor import extract
from app.nlp.icd_matcher import matcher
from app.services.bottleneck import BOTTLENECK_LABELS, classify
from app.protocols.library import PROTOCOLS


router = APIRouter(prefix="/sandbox", tags=["sandbox"])


NOTES_PATH = Path(__file__).parent.parent / "data" / "patient_notes.json"

# Keep in sync with the FastAPI app version in app/main.py. The integrator
# owns main.py, so the constant lives here to avoid a circular import.
ENGINE_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------

class SandboxTriageRequest(BaseModel):
    note_text: str = Field(min_length=20, description="Free-text clinical note to triage")
    # Accepted for parity with the patient form; the rule engine reads only
    # the note text, so demographics do not influence classification.
    age: Optional[int] = Field(None, ge=0, le=130)
    sex: Optional[str] = Field(None, max_length=10)


class ICDCandidateOut(BaseModel):
    code: str
    description: str
    score: float
    category: str


class StageTimings(BaseModel):
    extract: float
    classify: float
    icd: float
    total: float


class EngineInfo(BaseModel):
    protocols_evaluated: int
    categories: int
    version: str


class SandboxTriageResponse(BaseModel):
    triage: Dict[str, Any]          # TriageResult.to_dict() shape
    extraction: Dict[str, Any]      # ExtractionResult.to_dict() shape
    icd_candidates: List[ICDCandidateOut]
    stage_timings_ms: StageTimings
    engine: EngineInfo


class SampleNote(BaseModel):
    key: str
    label: str
    note_text: str
    expected_category: str


# ---------------------------------------------------------------------------
# POST /sandbox/triage
# ---------------------------------------------------------------------------

@router.post("/triage", response_model=SandboxTriageResponse)
def sandbox_triage(req: SandboxTriageRequest) -> SandboxTriageResponse:
    """Run the full pipeline on pasted note text. No DB writes."""
    t0 = time.perf_counter()
    extraction = extract(req.note_text)
    t1 = time.perf_counter()
    triage = classify(req.note_text, extraction)
    t2 = time.perf_counter()
    icd_matches = matcher().match(req.note_text, k=5)
    t3 = time.perf_counter()

    return SandboxTriageResponse(
        triage=triage.to_dict(),
        extraction=extraction.to_dict(),
        icd_candidates=[
            ICDCandidateOut(
                code=m.code, description=m.description,
                score=m.score, category=m.category,
            )
            for m in icd_matches
        ],
        stage_timings_ms=StageTimings(
            extract=round((t1 - t0) * 1000, 3),
            classify=round((t2 - t1) * 1000, 3),
            icd=round((t3 - t2) * 1000, 3),
            total=round((t3 - t0) * 1000, 3),
        ),
        engine=EngineInfo(
            protocols_evaluated=len(PROTOCOLS),
            categories=len(BOTTLENECK_LABELS),
            version=ENGINE_VERSION,
        ),
    )


# ---------------------------------------------------------------------------
# GET /sandbox/samples
# ---------------------------------------------------------------------------

# (key, human label prefix, truth_bottleneck, required truth_protocol or None)
_SAMPLE_SPECS: List[tuple] = [
    ("sepsis_missing_soc", "Sepsis bundle gap", "missing_soc", "sepsis"),
    ("med_risk", "Medication safety risk", "med_risk", None),
    ("awaiting_consult", "Awaiting specialist consult", "awaiting_consult", None),
    ("awaiting_imaging", "Awaiting imaging", "awaiting_imaging", None),
    ("dispo_delay", "Discharge / placement delay", "dispo_delay", None),
    ("readmit_risk", "High readmission risk", "readmit_risk", None),
    ("clear", "No active bottleneck", "clear", None),
]

# A hand-authored sample whose whole point is the NegEx pass: "Denies chest
# pain. No melena." produces two NEG-tagged findings the demo can point at,
# while still classifying as a clean sepsis missing_soc/red. Kept first so the
# negation story is one click away in the sandbox. Verified at module import
# below that it actually reproduces (no silent drift).
_NEGATION_SHOWCASE = SampleNote(
    key="negation_showcase",
    label="Negation handling — sepsis with ruled-out symptoms",
    note_text=(
        "72yo from SNF, fever 39.4, BP 88/52, lactate 3.1, WBC 18. "
        "Meets SIRS criteria, urinary source. Denies chest pain. No melena. "
        "Blood cultures drawn, IV fluids started. Antibiotics not yet given."
    ),
    expected_category="missing_soc",
)

_samples_cache: Optional[List[SampleNote]] = None


def _load_samples() -> List[SampleNote]:
    """Pick one corpus note per bottleneck category, deterministically.

    Selection rule: the FIRST corpus row (file order) whose truth label
    matches the spec AND whose live classification agrees with that truth
    label — so each sample demonstrably reproduces its expected category
    when pasted into the sandbox. The hand-authored negation-showcase sample
    is prepended (it reproduces missing_soc and shows two NEG tags).
    """
    global _samples_cache
    if _samples_cache is not None:
        return _samples_cache

    rows: List[Dict] = json.loads(NOTES_PATH.read_text())
    samples: List[SampleNote] = []
    # Prepend the negation showcase only if it still reproduces its category
    # (guards against rule drift silently breaking the demo).
    _ns = _NEGATION_SHOWCASE
    if classify(_ns.note_text, extract(_ns.note_text)).primary.category == _ns.expected_category:
        samples.append(_ns)
    for key, label_prefix, truth, protocol in _SAMPLE_SPECS:
        for row in rows:
            if row.get("truth_bottleneck") != truth:
                continue
            if protocol and row.get("truth_protocol") != protocol:
                continue
            note = row["note_text"]
            predicted = classify(note, extract(note)).primary.category
            if predicted != truth:
                continue
            samples.append(
                SampleNote(
                    key=key,
                    label=f"{label_prefix} — {row['chief_complaint']}",
                    note_text=note,
                    expected_category=truth,
                )
            )
            break
    _samples_cache = samples
    return samples


@router.get("/samples", response_model=List[SampleNote])
def sandbox_samples() -> List[SampleNote]:
    """Curated demo notes, one per bottleneck category."""
    return _load_samples()
