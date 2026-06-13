"""Longitudinal trend engine.

Takes a patient's note history (prior notes oldest-first, then the current
note) and produces a trajectory narrative: which labs are rising or falling,
whether that is clinically improving or worsening, recurrent-admission
signals, and protocol gaps that were open in an earlier note but documented
by now.

DESIGN INVARIANT — trends are NARRATIVE ONLY. The deterministic classifier
(app.services.bottleneck.classify) never sees prior notes; it reads only the
current note. Nothing here feeds back into category/urgency. That keeps the
corpus eval provably stable: history changes the story we tell, not the
decision the rules make. This is an operational coordination signal, not a
clinical decision aid.

The point of trajectory in an ops console: it distinguishes "this step was
never done" (a real bottleneck) from "this was done and resolved" (no
action needed), and it tells a charge nurse whether a patient is trending
toward or away from the door.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

from app.nlp.extractor import extract
from app.services.silent_failure import evaluate


# Which direction is clinically good for each lab. "down_good" means a falling
# value is improving (lactate clearing); "up_good" means rising is improving
# (hemoglobin recovering); "context" means direction alone is not a verdict.
LAB_POLARITY: Dict[str, str] = {
    "lactate": "down_good",
    "creatinine": "down_good",
    "troponin": "down_good",
    "WBC": "down_good",
    "potassium": "down_good",
    "BNP": "down_good",
    "procalcitonin": "down_good",
    "d_dimer": "down_good",
    "anion_gap": "down_good",
    "INR": "down_good",
    "QTc": "down_good",
    "hemoglobin": "up_good",
    "bicarbonate": "up_good",
    "ANC": "up_good",
    "glucose": "context",
    "sodium": "context",
    "magnesium": "context",
    "ph": "context",
}

# Per-lab absolute floor for "meaningful change", on top of a 5% relative band.
# Tuned so creatinine 1.0->1.2 reads as a move while glucose 142->148 does not.
LAB_EPS_FLOOR: Dict[str, float] = {
    "creatinine": 0.2,
    "lactate": 0.3,
    "troponin": 0.02,
    "potassium": 0.2,
    "INR": 0.3,
    "magnesium": 0.2,
    "ph": 0.03,
    "WBC": 1.0,
    "hemoglobin": 0.5,
    "glucose": 20.0,
    "sodium": 3.0,
    "anion_gap": 2.0,
    "bicarbonate": 2.0,
    "BNP": 100.0,
    "ANC": 200.0,
    "QTc": 15.0,
    "procalcitonin": 0.5,
    "d_dimer": 0.5,
}

# Labs worth trending in the UI, in display priority order.
TRENDED_LABS = [
    "lactate", "creatinine", "troponin", "WBC", "potassium", "hemoglobin",
    "glucose", "anion_gap", "INR", "bicarbonate", "BNP", "ANC", "QTc",
    "procalcitonin", "d_dimer", "sodium", "magnesium", "ph",
]


@dataclass
class TrendPoint:
    hours_ago: int
    captured_at: Optional[str]   # ISO string or None
    value: Optional[float]
    raw: Optional[str]
    negated: bool = False


@dataclass
class LabTrend:
    label: str
    polarity: str                # down_good | up_good | context
    direction: str               # rising | falling | stable | insufficient
    clinical: str                # improving | worsening | stable | unknown
    delta: Optional[float]
    narrative: str               # "lactate 4.1 → 3.1 → 2.2 (clearing)"
    points: List[TrendPoint]


@dataclass
class ResolvedGap:
    protocol_key: str
    protocol_name: str
    action_label: str
    opened_seq: int
    closed_seq: int


@dataclass
class Recurrence:
    ordinal: int
    window_phrase: str
    evidence: str


@dataclass
class NoteInput:
    note_text: str
    hours_ago: int
    captured_at: Optional[datetime] = None


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _eps(label: str, first: float) -> float:
    rel = 0.05 * abs(first)
    floor = LAB_EPS_FLOOR.get(label, 0.0)
    return max(rel, floor)


def _clinical(polarity: str, direction: str) -> str:
    if direction in ("insufficient",):
        return "unknown"
    if direction == "stable":
        return "stable"
    if polarity == "context":
        return "unknown"
    good_when = "falling" if polarity == "down_good" else "rising"
    return "improving" if direction == good_when else "worsening"


_CLEARING_WORD = {
    ("down_good", "improving"): "clearing",
    ("up_good", "improving"): "recovering",
}


def _narrative(label: str, polarity: str, clinical: str, points: List[TrendPoint]) -> str:
    chain_parts: List[str] = []
    for p in points:
        chain_parts.append(p.raw if p.raw is not None else "pending")
    chain = " → ".join(chain_parts)
    if clinical == "improving":
        word = _CLEARING_WORD.get((polarity, clinical), "improving")
    elif clinical == "worsening":
        word = "worsening"
    elif clinical == "stable":
        word = "stable"
    else:
        word = ""
    suffix = f" ({word})" if word else ""
    return f"{label} {chain}{suffix}"


def _lab_values_by_label(note_text: str) -> Dict[str, TrendPoint]:
    """Extract one numeric point per trended lab from a single note."""
    ext = extract(note_text)
    out: Dict[str, TrendPoint] = {}
    for f in ext.labs:
        if f.label not in TRENDED_LABS or f.label in out:
            continue
        out[f.label] = TrendPoint(
            hours_ago=0,
            captured_at=None,
            value=_to_float(f.value),
            raw=f.value,
            negated=bool(f.metadata.get("negated")),
        )
    return out


# Ordinal-admission recurrence cues, e.g. "third DKA admission in 8 months".
_ORDINALS = {
    "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
}

import re

_RECUR_RE = re.compile(
    r"\b(second|third|fourth|fifth|2nd|3rd|4th|5th)\b[^.\n]{0,60}?"
    r"\b(admission|admitted|presentation|visit|hospitalization)\b"
    r"([^.\n]{0,40}?\b(?:in|over|within|past)\b[^.\n]{0,30})?",
    re.I,
)


def _recurrence(note_texts: List[str]) -> Optional[Recurrence]:
    best: Optional[Recurrence] = None
    for text in note_texts:
        for m in _RECUR_RE.finditer(text):
            ordinal = _ORDINALS.get(m.group(1).lower())
            if not ordinal:
                continue
            window = (m.group(3) or "").strip()
            if best is None or ordinal > best.ordinal:
                best = Recurrence(
                    ordinal=ordinal,
                    window_phrase=window,
                    evidence=m.group(0).strip(),
                )
    return best


def _resolved_gaps(notes: List[NoteInput]) -> List[ResolvedGap]:
    """Gaps that were missing in the earliest note but documented by the
    current (last) note. Pure narrative — proves 'done and resolved'."""
    if len(notes) < 2:
        return []
    earliest = notes[0].note_text
    current = notes[-1].note_text

    early_missing: Dict[tuple, str] = {}
    for pm in evaluate(earliest):
        if not pm.triggered:
            continue
        for action in pm.missing:
            early_missing[(pm.protocol.key, action.key)] = (pm.protocol.name, action.label)

    if not early_missing:
        return []

    current_matches = {pm.protocol.key: pm for pm in evaluate(current)}
    resolved: List[ResolvedGap] = []
    for (pkey, akey), (pname, alabel) in early_missing.items():
        pm = current_matches.get(pkey)
        still_missing = pm and pm.triggered and any(a.key == akey for a in pm.missing)
        if not still_missing:
            resolved.append(
                ResolvedGap(
                    protocol_key=pkey,
                    protocol_name=pname,
                    action_label=alabel,
                    opened_seq=0,
                    closed_seq=len(notes) - 1,
                )
            )
    return resolved


def compute(notes: List[NoteInput]) -> Dict:
    """Compute the trends payload.

    notes: oldest-first, the LAST element being the current note. A single
    note (no priors) yields a well-formed payload with no trend signal.
    """
    if not notes:
        return _empty_payload(0)

    # Per-note lab points, keyed by label.
    per_note: List[Dict[str, TrendPoint]] = []
    for n in notes:
        pts = _lab_values_by_label(n.note_text)
        for p in pts.values():
            p.hours_ago = n.hours_ago
            p.captured_at = n.captured_at.isoformat() if n.captured_at else None
        per_note.append(pts)

    labs: List[LabTrend] = []
    for label in TRENDED_LABS:
        # Which notes mention this lab at all?
        appears = [label in note_pts for note_pts in per_note]
        if not any(appears):
            continue
        # Build an aligned series spanning from the first note that mentions
        # the lab through the current note. Notes in that span that omit the
        # lab become explicit "pending" points (no labs back yet) — itself a
        # signal, and it keeps the arrow chain honest.
        first_idx = appears.index(True)
        series: List[TrendPoint] = []
        for i in range(first_idx, len(per_note)):
            note_pts = per_note[i]
            if label in note_pts:
                series.append(note_pts[label])
            else:
                n = notes[i]
                series.append(
                    TrendPoint(
                        hours_ago=n.hours_ago,
                        captured_at=n.captured_at.isoformat() if n.captured_at else None,
                        value=None,
                        raw=None,
                    )
                )
        # Only trend labs that appear in the current note OR in >=2 notes.
        appears_current = appears[-1]
        numeric_count = sum(1 for p in series if p.value is not None and not p.negated)
        if numeric_count < 2 and not appears_current:
            continue

        polarity = LAB_POLARITY.get(label, "context")
        numeric = [p for p in series if p.value is not None and not p.negated]
        if len(numeric) < 2:
            direction = "insufficient"
            delta = None
        else:
            first, last = numeric[0].value, numeric[-1].value
            delta = round(last - first, 3)
            eps = _eps(label, first)
            if delta > eps:
                direction = "rising"
            elif delta < -eps:
                direction = "falling"
            else:
                direction = "stable"
        clinical = _clinical(polarity, direction)
        labs.append(
            LabTrend(
                label=label,
                polarity=polarity,
                direction=direction,
                clinical=clinical,
                delta=delta,
                narrative=_narrative(label, polarity, clinical, series),
                points=series,
            )
        )

    note_texts = [n.note_text for n in notes]
    recurrence = _recurrence(note_texts)
    resolved = _resolved_gaps(notes)

    # Aggregate roll-up for display: worst-of clinical across trended labs.
    clinicals = {l.clinical for l in labs}
    if "worsening" in clinicals and "improving" in clinicals:
        trajectory = "mixed"
    elif "worsening" in clinicals:
        trajectory = "worsening"
    elif "improving" in clinicals:
        trajectory = "improving"
    elif clinicals and clinicals <= {"stable"}:
        trajectory = "stable"
    else:
        trajectory = "none"

    return {
        "labs": [_lab_to_dict(l) for l in labs],
        "recurrence": asdict(recurrence) if recurrence else None,
        "resolved_gaps": [asdict(r) for r in resolved],
        "trajectory_signal": trajectory,
        "note_count": len(notes),
    }


def _lab_to_dict(l: LabTrend) -> Dict:
    return {
        "label": l.label,
        "polarity": l.polarity,
        "direction": l.direction,
        "clinical": l.clinical,
        "delta": l.delta,
        "narrative": l.narrative,
        "points": [asdict(p) for p in l.points],
    }


def _empty_payload(note_count: int) -> Dict:
    return {
        "labs": [],
        "recurrence": None,
        "resolved_gaps": [],
        "trajectory_signal": "none",
        "note_count": note_count,
    }
