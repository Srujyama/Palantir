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

import inspect
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from app.nlp.extractor import ExtractionResult, Finding, Span
from app.services.interactions import InteractionFlag, screen as screen_interactions
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


# Interaction flags that duplicate a triggered protocol's own missing
# medication-review step are folded INTO that protocol gap rather than
# surfacing as a second, competing bottleneck. Policy (clinician-facing):
# when the protocol already owes a medication review (e.g. the AKI workup's
# "Medication review for nephrotoxins"), the nephrotoxin flag is the
# evidence FOR that gap — route once, to the protocol owner, instead of
# splitting the same problem across physician and pharmacist queues.
# Mapping: interaction rule_key -> (protocol_key, expected_action_key).
_FLAG_SUBSUMED_BY_PROTOCOL_GAP: Dict[str, tuple] = {
    "nephrotoxic_combo_aki": ("aki", "med_review"),
}


def _flag_subsumed(flag: InteractionFlag, pms: List[ProtocolMatch]) -> bool:
    target = _FLAG_SUBSUMED_BY_PROTOCOL_GAP.get(flag.rule_key)
    if not target:
        return False
    proto_key, action_key = target
    return any(
        pm.triggered
        and pm.protocol.key == proto_key
        and any(a.key == action_key for a in pm.missing)
        for pm in pms
    )


def _med_risk(
    note: str, ext: ExtractionResult, flags: Optional[List[InteractionFlag]] = None
) -> Optional[Bottleneck]:
    """Detect medication-driven risk via the data-encoded interaction engine.

    Delegates to app.services.interactions.screen — a declarative,
    citation-backed rule table (nephrotoxic combos, QT-prolong stacks,
    anticoagulant + bleed signals, triple whammy, sedation stacks, ...) —
    and promotes the highest-severity flag to a med_risk bottleneck. An
    operational coordination signal for the pharmacist queue, not a
    clinical decision aid. Callers that already screened (the classifier)
    pass `flags` in; otherwise we screen here.
    """
    if flags is None:
        flags = screen_interactions(ext, note)
    if not flags:
        return None
    top = flags[0]
    med_list = ", ".join(sorted({m.name for m in top.meds_involved}))
    evidence_spans = [m.evidence for m in top.meds_involved[:3]] + top.context_evidence[:2]
    return Bottleneck(
        category="med_risk",
        label=BOTTLENECK_LABELS["med_risk"],
        urgency=top.severity,
        owner="pharmacist",
        recommended_action=f"Pharmacy review: {top.recommendation}",
        rationale=(
            f"{top.name}: {top.mechanism} Medications involved: {med_list}."
        ),
        evidence=evidence_spans,
        citation=top.citation,
    )


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
        # NOTE: the shipped corpus labels awaiting_imaging rows with
        # expected_owner=physician, but the canonical routing table in
        # app/services/evaluation.py (and its frozen test) encodes "nurse".
        # The two cannot both be satisfied by one general rule; we keep the
        # canonical "nurse" routing here and flag the corpus/spec mismatch
        # for the data owners rather than special-casing notes.
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
    # Pass the precomputed protocol matches if silent_failures supports it
    # (so the protocol regexes run once); fall back to the legacy signature.
    try:
        _sf_params = inspect.signature(silent_failures).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins/odd callables
        _sf_params = {}
    if "matches" in _sf_params:
        sfs = silent_failures(note, matches=pms)
    else:
        sfs = silent_failures(note)

    # Screen interactions once; drop flags subsumed by a triggered protocol's
    # own missing medication-review step (see _FLAG_SUBSUMED_BY_PROTOCOL_GAP).
    flags = [
        f for f in screen_interactions(ext, note) if not _flag_subsumed(f, pms)
    ]

    bottlenecks: List[Bottleneck] = []
    for key, fn in CASCADE:
        if key == "missing_soc":
            b = fn(note, ext, sfs)
        elif key == "med_risk":
            b = fn(note, ext, flags)
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

    # Sort by urgency (red < amber < green) then by cascade order.
    #
    # Equal-urgency tie-break policy (clinician-reviewed): a protocol gap
    # (missing_soc — an undone bundle step) normally outranks a medication
    # flag of the same urgency, per cascade order. EXCEPTION: a red
    # interaction flag carrying objective context evidence — i.e. harm in
    # progress, such as an anticoagulant with documented melena — outranks
    # an equal-urgency protocol gap, because stopping active harm precedes
    # completing bundle documentation and routes to a pharmacist who can act
    # in parallel. Flags that merely duplicate a protocol's own missing
    # med-review step never reach this comparison (subsumed above).
    cascade_order: Dict[str, float] = {k: float(i) for i, (k, _) in enumerate(CASCADE)}
    if flags and flags[0].severity == "red" and flags[0].context_evidence:
        cascade_order["med_risk"] = cascade_order["missing_soc"] - 0.5
    bottlenecks.sort(key=lambda b: (URGENCY_RANK[b.urgency], cascade_order[b.category]))
    return TriageResult(
        primary=bottlenecks[0],
        secondary=bottlenecks[1:],
        silent_failures=sfs,
        protocol_matches=pms,
    )
