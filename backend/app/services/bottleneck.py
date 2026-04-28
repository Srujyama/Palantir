"""
Bottleneck classifier.

Takes extracted note signals + protocol evaluation results and decides:

  - the primary bottleneck (one of six categories)
  - secondary bottlenecks (everything else still active)
  - urgency (red / amber / green)
  - owner (who acts)
  - recommended next action (concrete, imperative)
  - human-readable rationale ("Why is this patient stuck?")
  - evidence spans (offsets in the note for highlighting)

The decision logic is deterministic and cascading: the most dangerous /
time-sensitive bottleneck wins. This is closer to how triage actually works
than a single multiclass model, and it's fully explainable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from app.nlp.extractor import ExtractionResult, Finding, Span
from app.services.silent_failure import (
    ProtocolMatch,
    SilentFailure,
    evaluate as evaluate_protocols,
    silent_failures,
)


BOTTLENECK_LABELS: Dict[str, str] = {
    "missing_soc": "Missing standard-of-care step",
    "med_risk": "Medication safety risk",
    "awaiting_consult": "Awaiting specialist consult",
    "awaiting_imaging": "Awaiting imaging",
    "dispo_delay": "Discharge / placement delay",
    "readmit_risk": "High readmission risk",
    "clear": "No active bottleneck",
}


URGENCY_RANK = {"red": 0, "amber": 1, "green": 2}


@dataclass
class Bottleneck:
    category: str                 # one of BOTTLENECK_LABELS keys
    label: str                    # human-readable label
    urgency: str                  # red | amber | green
    owner: str                    # physician | nurse | pharmacist | case_manager | social_worker
    recommended_action: str
    rationale: str
    evidence: List[Span] = field(default_factory=list)
    citation: Optional[str] = None


@dataclass
class TriageResult:
    primary: Bottleneck
    secondary: List[Bottleneck]
    silent_failures: List[SilentFailure]
    protocol_matches: List[ProtocolMatch]

    def to_dict(self) -> Dict:
        def _b(b: Bottleneck) -> Dict:
            return {
                "category": b.category,
                "label": b.label,
                "urgency": b.urgency,
                "owner": b.owner,
                "recommended_action": b.recommended_action,
                "rationale": b.rationale,
                "evidence": [asdict(s) for s in b.evidence],
                "citation": b.citation,
            }

        return {
            "primary": _b(self.primary),
            "secondary": [_b(b) for b in self.secondary],
            "silent_failures": [
                {
                    "protocol_key": sf.protocol_key,
                    "protocol_name": sf.protocol_name,
                    "missing_action": sf.missing_action,
                    "severity": sf.severity,
                    "citation": sf.citation,
                    "trigger_evidence": asdict(sf.trigger_evidence),
                    "owner": sf.owner,
                    "urgency": sf.urgency,
                }
                for sf in self.silent_failures
            ],
            "protocol_matches": [
                {
                    "protocol_key": pm.protocol.key,
                    "protocol_name": pm.protocol.name,
                    "triggered": pm.triggered,
                    "documented": [a.label for a in pm.documented],
                    "missing": [a.label for a in pm.missing],
                    "trigger_evidence": [asdict(s) for s in pm.trigger_evidence],
                    "citation": pm.protocol.citation,
                    "time_window_hours": pm.protocol.time_window_hours,
                }
                for pm in pm_iterable_with_triggered_first(self.protocol_matches)
            ],
        }


def pm_iterable_with_triggered_first(matches: List[ProtocolMatch]) -> List[ProtocolMatch]:
    return sorted(matches, key=lambda m: (not m.triggered, m.protocol.key))


# ---------------------------------------------------------------------------
# Per-category detectors. Each returns Optional[Bottleneck].
# ---------------------------------------------------------------------------

def _missing_soc(note: str, ext: ExtractionResult, sfs: List[SilentFailure]) -> Optional[Bottleneck]:
    if not sfs:
        return None
    # Take the highest-urgency miss
    sfs_sorted = sorted(sfs, key=lambda s: URGENCY_RANK[s.urgency])
    sf = sfs_sorted[0]
    others = [s.missing_action for s in sfs_sorted[1:] if s.protocol_key == sf.protocol_key]
    extra = f" Additional gaps: {', '.join(others)}." if others else ""

    return Bottleneck(
        category="missing_soc",
        label=BOTTLENECK_LABELS["missing_soc"],
        urgency=sf.urgency,
        owner=sf.owner,
        recommended_action=sf.missing_action,
        rationale=(
            f"{sf.protocol_name} triggered by note evidence "
            f"“{sf.trigger_evidence.text}” but the required step "
            f"“{sf.missing_action}” is not documented.{extra}"
        ),
        evidence=[sf.trigger_evidence],
        citation=sf.citation,
    )


def _med_risk(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    """Detect medication-driven risk: nephrotoxic combos, QT-prolong stacks,
    DOAC + antiplatelet + NSAID, etc."""

    def _med_classes() -> List[str]:
        return [m.metadata.get("class", "") for m in ext.meds]

    classes = _med_classes()
    # Nephrotoxic + AKI markers
    creat_findings = [l for l in ext.labs if l.label == "creatinine"]
    creat_high = any(float(l.value) >= 1.5 for l in creat_findings if l.value)
    nephrotoxic = [m for m in ext.meds if "nephrotox" in m.metadata.get("class", "")]
    if creat_high and nephrotoxic:
        evidence_spans = [m.evidence for m in nephrotoxic[:3]] + [l.evidence for l in creat_findings[:1]]
        med_list = ", ".join(sorted({m.label for m in nephrotoxic}))
        return Bottleneck(
            category="med_risk",
            label=BOTTLENECK_LABELS["med_risk"],
            urgency="red",
            owner="pharmacist",
            recommended_action=(
                f"Pharmacy review: hold or dose-adjust nephrotoxic agents "
                f"({med_list}); recheck BMP."
            ),
            rationale=(
                f"Creatinine elevated ({creat_findings[0].value}) with active "
                f"nephrotoxic exposure: {med_list}. Continued exposure risks "
                "worsening AKI."
            ),
            evidence=evidence_spans,
            citation="KDIGO AKI guidance",
        )

    # QT-prolonging stack
    qt_meds = [m for m in ext.meds if "qt_prolong" in m.metadata.get("class", "")]
    qtc_findings = [l for l in ext.labs if l.label == "QTc"]
    qtc_high = any(int(l.value) >= 500 for l in qtc_findings if l.value and l.value.isdigit())
    if len(qt_meds) >= 2 or (qt_meds and qtc_high):
        evidence_spans = [m.evidence for m in qt_meds[:3]] + [l.evidence for l in qtc_findings[:1]]
        med_list = ", ".join(sorted({m.label for m in qt_meds}))
        urgency = "red" if qtc_high else "amber"
        return Bottleneck(
            category="med_risk",
            label=BOTTLENECK_LABELS["med_risk"],
            urgency=urgency,
            owner="pharmacist",
            recommended_action=(
                f"Pharmacy review: rationalize QT-prolonging agents "
                f"({med_list}); replete K and Mg; repeat ECG."
            ),
            rationale=(
                f"Multiple QT-prolonging medications ({med_list}) "
                + (f"with QTc {qtc_findings[0].value} ms. " if qtc_findings else "documented. ")
                + "Risk of torsades de pointes."
            ),
            evidence=evidence_spans,
            citation="CredibleMeds QT drug list",
        )

    # Anticoagulant + active bleed signals
    anticoag = [m for m in ext.meds if "anticoag" in m.metadata.get("class", "")]
    bleed_symptoms = [s for s in ext.symptoms if s.label == "melena"]
    nsaid = [m for m in ext.meds if "nsaid" in m.metadata.get("class", "")]
    if anticoag and (bleed_symptoms or nsaid):
        evidence_spans = (
            [m.evidence for m in anticoag[:2]]
            + [s.evidence for s in bleed_symptoms[:1]]
            + [m.evidence for m in nsaid[:1]]
        )
        return Bottleneck(
            category="med_risk",
            label=BOTTLENECK_LABELS["med_risk"],
            urgency="red",
            owner="pharmacist",
            recommended_action=(
                "Pharmacy review: hold anticoagulant and concomitant NSAID; "
                "type and screen; reverse if active bleed."
            ),
            rationale=(
                "Active anticoagulant exposure with concurrent NSAID and/or "
                "bleeding signs documented in note."
            ),
            evidence=evidence_spans,
            citation="ACCP anticoagulation guidance",
        )

    return None


def _awaiting_consult(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    pending = [c for c in ext.consults if c.value == "pending"]
    if not pending:
        return None
    services = sorted({c.label.replace("_", " ") for c in pending})
    spans = [c.evidence for c in pending[:3]]
    return Bottleneck(
        category="awaiting_consult",
        label=BOTTLENECK_LABELS["awaiting_consult"],
        urgency="amber",
        owner="physician",
        recommended_action=(
            f"Page {services[0]} attending; if no callback in 30 min, "
            "escalate to chief on call."
        ),
        rationale=(
            f"Consult to {', '.join(services)} is documented as pending with "
            "no note in the chart. Patient otherwise medically optimized."
        ),
        evidence=spans,
    )


def _awaiting_imaging(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    pending = [i for i in ext.imaging if i.value == "pending"]
    if not pending:
        return None
    studies = sorted({i.label.upper() for i in pending})
    spans = [i.evidence for i in pending[:2]]
    return Bottleneck(
        category="awaiting_imaging",
        label=BOTTLENECK_LABELS["awaiting_imaging"],
        urgency="amber",
        owner="nurse",
        recommended_action=(
            f"Call radiology to expedite {studies[0]}; confirm patient is "
            "ready (NPO, IV access, contrast eligibility)."
        ),
        rationale=(
            f"{', '.join(studies)} ordered but not yet resulted; downstream "
            "disposition depends on this study."
        ),
        evidence=spans,
    )


def _dispo_delay(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    blockers = [d for d in ext.dispo if d.label != "medically_ready"]
    if not blockers:
        return None
    primary = blockers[0]
    pretty = {
        "snf_placement": "SNF placement",
        "home_oxygen": "home oxygen setup",
        "insurance_auth": "insurance authorization",
        "dme_delay": "DME / equipment delivery",
        "pt_clearance": "physical therapy clearance",
        "social_placement": "social / placement support",
        "training_incomplete": "patient or family training",
        "case_mgmt_pending": "case management follow-up",
    }.get(primary.label, primary.label.replace("_", " "))

    return Bottleneck(
        category="dispo_delay",
        label=BOTTLENECK_LABELS["dispo_delay"],
        urgency="green",
        owner="case_manager",
        recommended_action=(
            f"Case management: own {pretty}; daily 3PM huddle update on this "
            "patient until resolved."
        ),
        rationale=(
            f"Patient appears medically ready but discharge is held by {pretty}."
        ),
        evidence=[b.evidence for b in blockers[:3]],
    )


def _readmit_risk(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    if not ext.risk_factors:
        return None
    return Bottleneck(
        category="readmit_risk",
        label=BOTTLENECK_LABELS["readmit_risk"],
        urgency="amber",
        owner="case_manager",
        recommended_action=(
            "Schedule transitional-care visit within 7 days; arrange "
            "medication reconciliation and home-health referral before "
            "discharge."
        ),
        rationale=(
            "Multiple readmission-risk markers in the note: prior recent "
            "admissions, adherence concerns, or limited support."
        ),
        evidence=[r.evidence for r in ext.risk_factors[:3]],
    )


# ---------------------------------------------------------------------------
# Cascading classifier
# ---------------------------------------------------------------------------

CASCADE = [
    ("missing_soc", _missing_soc),       # most dangerous — bundle missing
    ("med_risk",    _med_risk),          # patient-safety
    ("awaiting_consult", _awaiting_consult),
    ("awaiting_imaging", _awaiting_imaging),
    ("readmit_risk", _readmit_risk),     # before dispo: addressable upstream
    ("dispo_delay", _dispo_delay),
]


def classify(note: str, ext: ExtractionResult) -> TriageResult:
    pms = evaluate_protocols(note)
    sfs = silent_failures(note)

    bottlenecks: List[Bottleneck] = []
    for key, fn in CASCADE:
        if key == "missing_soc":
            b = fn(note, ext, sfs)
        else:
            b = fn(note, ext)
        if b:
            bottlenecks.append(b)

    if not bottlenecks:
        primary = Bottleneck(
            category="clear",
            label=BOTTLENECK_LABELS["clear"],
            urgency="green",
            owner="",
            recommended_action="No action required; consider for discharge.",
            rationale="No active operational, safety, or protocol gaps detected.",
            evidence=[],
        )
        return TriageResult(primary=primary, secondary=[], silent_failures=sfs, protocol_matches=pms)

    # Sort by urgency (red < amber < green) then by cascade order
    cascade_order = {k: i for i, (k, _) in enumerate(CASCADE)}
    bottlenecks.sort(key=lambda b: (URGENCY_RANK[b.urgency], cascade_order[b.category]))
    return TriageResult(
        primary=bottlenecks[0],
        secondary=bottlenecks[1:],
        silent_failures=sfs,
        protocol_matches=pms,
    )
