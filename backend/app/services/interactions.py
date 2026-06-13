"""
Data-encoded drug-interaction screening engine.

Replaces the hardcoded med-risk rules in the bottleneck cascade with a
declarative, citation-backed rule table. Every rule names the drug classes
it fires on, the lab/symptom context it requires, a one-sentence mechanism,
a pharmacist-voiced recommendation, and a literature citation — so every
flag traces to evidence spans in the source note.

Deterministic and explainable by construction: no LLM calls, no scoring
model. This is an operational coordination signal for the pharmacist queue,
NOT a clinical decision aid.

Design notes:
  * Drug classes come from the extractor's MEDICATIONS tagging
    (app.nlp.extractor). A small SUPPLEMENTAL_MEDICATIONS dict adds drugs
    the extractor does not yet know (serotonergic agents, thiazides, common
    brand names) using the same word-boundary scan style.
  * Each rule's `required_classes` is a tuple of groups; the rule fires when
    every group is satisfied by a DISTINCT active medication whose class tag
    contains any substring in that group (distinctness is what makes
    "two QT prolongers" and "dual anticoagulation" honest).
  * Findings whose metadata carries a truthy "negated" flag are skipped —
    the extractor may mark e.g. "denies melena" that way.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

from app.nlp.extractor import ExtractionResult, Finding, Span, _tag_negation


SEVERITY_RANK: Dict[str, int] = {"red": 0, "amber": 1}


# ---------------------------------------------------------------------------
# Supplemental drug surface (extractor's MEDICATIONS is NOT edited here).
# drug name (lowercase) -> class tag, same convention as extractor.MEDICATIONS.
# ---------------------------------------------------------------------------

SUPPLEMENTAL_MEDICATIONS: Dict[str, str] = {
    # Serotonergic agents missing from the extractor's surface
    "tramadol": "opioid_serotonergic",
    "linezolid": "antibiotic_maoi_serotonergic",
    "sertraline": "ssri",
    "fluoxetine": "ssri",
    "paroxetine": "ssri",
    "venlafaxine": "snri_serotonergic",
    "duloxetine": "snri_serotonergic",
    "trazodone": "serotonergic",
    "buspirone": "serotonergic",
    "sumatriptan": "triptan_serotonergic",
    # Thiazides (triple-whammy participation)
    "hydrochlorothiazide": "thiazide_diuretic",
    "chlorthalidone": "thiazide_diuretic",
    # Common brand names normalized via ALIASES below
    "eliquis": "anticoagulant_doac",
    "xarelto": "anticoagulant_doac",
    "coumadin": "anticoagulant_vka",
    "plavix": "antiplatelet",
    "ticagrelor": "antiplatelet",
    "prasugrel": "antiplatelet",
}

# Brand -> generic so the same drug mentioned twice (e.g. "enoxaparin
# (Lovenox)") never satisfies a two-distinct-drug rule against itself.
ALIASES: Dict[str, str] = {
    "lovenox": "enoxaparin",
    "ativan": "lorazepam",
    "valium": "diazepam",
    "versed": "midazolam",
    "dilaudid": "hydromorphone",
    "protonix": "pantoprazole",
    "nexium": "esomeprazole",
    "zosyn": "piperacillin",
    "solu-medrol": "methylprednisolone",
    "eliquis": "apixaban",
    "xarelto": "rivaroxaban",
    "coumadin": "warfarin",
    "plavix": "clopidogrel",
}


# ---------------------------------------------------------------------------
# Rule model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContextCondition:
    """Declarative lab/symptom context requirement.

    Satisfied when ANY of the configured checks holds:
      * a non-negated lab finding with `lab` label and value >= `lab_gte`
      * a non-negated lab finding with `lab` label and value <= `lab_lte`
      * a non-negated symptom finding with label `symptom`
    """

    description: str
    lab: Optional[str] = None
    lab_gte: Optional[float] = None
    lab_lte: Optional[float] = None
    symptom: Optional[str] = None


@dataclass(frozen=True)
class InteractionRule:
    key: str
    name: str
    severity: str                                   # red | amber
    required_classes: Tuple[Tuple[str, ...], ...]   # groups of class substrings
    mechanism: str                                  # one sentence, why it's dangerous
    recommendation: str                             # imperative, pharmacist-voiced
    citation: str
    context_condition: Optional[ContextCondition] = None


@dataclass
class MedInvolved:
    name: str
    drug_class: str
    evidence: Span


@dataclass
class InteractionFlag:
    rule_key: str
    name: str
    severity: str
    mechanism: str
    recommendation: str
    citation: str
    meds_involved: List[MedInvolved]
    context_evidence: List[Span]

    def to_dict(self) -> Dict:
        return {
            "rule_key": self.rule_key,
            "name": self.name,
            "severity": self.severity,
            "mechanism": self.mechanism,
            "recommendation": self.recommendation,
            "citation": self.citation,
            "meds_involved": [
                {"name": m.name, "class": m.drug_class, "evidence": asdict(m.evidence)}
                for m in self.meds_involved
            ],
            "context_evidence": [asdict(s) for s in self.context_evidence],
        }


# ---------------------------------------------------------------------------
# Rule table. The first five rules preserve the three legacy hardcoded
# behaviors exactly (nephrotoxic+AKI red; QT stack amber / +QTc>=500 red;
# anticoagulant + melena-or-NSAID red). The rest are new.
# ---------------------------------------------------------------------------

RULES: Tuple[InteractionRule, ...] = (
    InteractionRule(
        key="nephrotoxic_combo_aki",
        name="Nephrotoxic exposure during AKI",
        severity="red",
        required_classes=(("nephrotox",),),
        context_condition=ContextCondition(
            description="creatinine >= 1.5", lab="creatinine", lab_gte=1.5,
        ),
        mechanism=(
            "Continued nephrotoxic exposure during acute kidney injury "
            "compounds tubular damage and delays renal recovery."
        ),
        recommendation=(
            "Hold or dose-adjust nephrotoxic agents; recheck BMP and "
            "trend creatinine."
        ),
        citation="KDIGO AKI guidance",
    ),
    InteractionRule(
        key="qt_prolonged_qtc",
        name="QT-prolonging agent with prolonged QTc",
        severity="red",
        required_classes=(("qt_prolong",),),
        context_condition=ContextCondition(
            description="QTc >= 500 ms", lab="QTc", lab_gte=500,
        ),
        mechanism=(
            "A QT-prolonging agent on top of a QTc at or above 500 ms "
            "sharply raises the risk of torsades de pointes."
        ),
        recommendation=(
            "Rationalize QT-prolonging agents; replete K and Mg; repeat ECG."
        ),
        citation="CredibleMeds QT drug list",
    ),
    InteractionRule(
        key="qt_stack",
        name="Multiple QT-prolonging agents",
        severity="amber",
        required_classes=(("qt_prolong",), ("qt_prolong",)),
        mechanism=(
            "Concurrent QT-prolonging medications have additive effect on "
            "repolarization and torsades de pointes risk."
        ),
        recommendation=(
            "Rationalize QT-prolonging agents; replete K and Mg; repeat ECG."
        ),
        citation="CredibleMeds QT drug list",
    ),
    InteractionRule(
        key="anticoag_active_bleed",
        name="Anticoagulant with active GI bleeding signs",
        severity="red",
        required_classes=(("anticoag",),),
        context_condition=ContextCondition(
            description="melena documented", symptom="melena",
        ),
        mechanism=(
            "Ongoing anticoagulation during an active GI bleed sustains "
            "blood loss and delays hemostasis."
        ),
        recommendation=(
            "Hold anticoagulant; type and screen; assess for reversal if "
            "bleeding is active."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="anticoag_nsaid",
        name="Anticoagulant with concurrent NSAID",
        severity="red",
        required_classes=(("anticoag",), ("nsaid",)),
        mechanism=(
            "NSAIDs impair platelet function and erode gastric mucosa, "
            "multiplying bleeding risk on top of anticoagulation."
        ),
        recommendation=(
            "Hold the NSAID; substitute acetaminophen; reassess "
            "anticoagulant indication and bleeding risk."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="dual_anticoagulation",
        name="Two concurrent anticoagulants",
        severity="red",
        required_classes=(("anticoag",), ("anticoag",)),
        mechanism=(
            "Two therapeutic anticoagulants compound bleeding risk without "
            "added efficacy unless a deliberate bridge is underway."
        ),
        recommendation=(
            "Verify intent (bridge vs duplication); discontinue one agent "
            "unless a documented bridging plan exists."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="hyperkalemia_k_retainers",
        name="Potassium-retaining agent with hyperkalemia",
        severity="red",
        required_classes=(("k_sparing", "ace_inhibitor", "arb"),),
        context_condition=ContextCondition(
            description="potassium >= 5.5", lab="potassium", lab_gte=5.5,
        ),
        mechanism=(
            "K-sparing diuretics and RAAS inhibitors blunt potassium "
            "excretion and will worsen existing hyperkalemia."
        ),
        recommendation=(
            "Hold potassium-retaining agents (ACEi/ARB, K-sparing "
            "diuretic); recheck potassium and obtain an ECG."
        ),
        citation="KDIGO / hyperkalemia management consensus",
    ),
    InteractionRule(
        key="doac_antiplatelet",
        name="DOAC with antiplatelet dual therapy",
        severity="amber",
        required_classes=(("anticoagulant_doac",), ("antiplatelet",)),
        mechanism=(
            "Combining a DOAC with antiplatelet therapy roughly doubles "
            "major bleeding risk versus anticoagulation alone."
        ),
        recommendation=(
            "Confirm the indication for combined antithrombotic therapy; "
            "drop the antiplatelet if not mandated by recent stent or ACS."
        ),
        citation="AUGUSTUS trial / ACC consensus on combined antithrombotic therapy",
    ),
    InteractionRule(
        key="triple_whammy",
        name="Triple whammy (ACEi/ARB + diuretic + NSAID)",
        severity="amber",
        required_classes=(("ace_inhibitor", "arb"), ("diuretic",), ("nsaid",)),
        mechanism=(
            "RAAS blockade, volume depletion, and prostaglandin inhibition "
            "together collapse glomerular perfusion and precipitate AKI."
        ),
        recommendation=(
            "Stop the NSAID; reassess diuretic dosing and renal function "
            "before continuing the ACEi/ARB."
        ),
        citation="Triple-whammy nephrotoxicity literature (Lapi et al., BMJ 2013)",
    ),
    InteractionRule(
        key="opioid_benzo_stack",
        name="Opioid + benzodiazepine sedation stack",
        severity="amber",
        required_classes=(("opioid",), ("benzodiazepine",)),
        mechanism=(
            "Opioids and benzodiazepines synergistically depress "
            "respiratory drive and level of consciousness."
        ),
        recommendation=(
            "Reduce or stage doses; add sedation monitoring and keep "
            "naloxone available."
        ),
        citation="FDA boxed warning on opioid-benzodiazepine co-prescribing; Beers Criteria 2023",
    ),
    InteractionRule(
        key="serotonergic_stack",
        name="Serotonergic medication stack",
        severity="amber",
        required_classes=(
            ("ssri", "snri", "serotonergic", "maoi"),
            ("ssri", "snri", "serotonergic", "maoi"),
        ),
        mechanism=(
            "Concurrent serotonergic agents have additive serotonin burden "
            "and can precipitate serotonin syndrome."
        ),
        recommendation=(
            "Deprescribe or substitute one serotonergic agent; monitor for "
            "clonus, hyperthermia, and agitation."
        ),
        citation="Boyer & Shannon, NEJM 2005 (serotonin syndrome)",
    ),
    InteractionRule(
        key="insulin_hypoglycemia",
        name="Insulin with documented hypoglycemia",
        severity="amber",
        required_classes=(("insulin",),),
        context_condition=ContextCondition(
            description="glucose <= 70", lab="glucose", lab_lte=70,
        ),
        mechanism=(
            "An insulin regimen that has already produced hypoglycemia "
            "signals a dose/monitoring mismatch; continuing unchanged risks "
            "recurrent severe hypoglycemia."
        ),
        recommendation=(
            "Review insulin doses against intake and renal function; "
            "confirm scheduled POC glucose monitoring before further dosing."
        ),
        citation="ISMP List of High-Alert Medications (insulin); ADA inpatient glycemic guidance",
    ),
    InteractionRule(
        key="warfarin_supratherapeutic_inr",
        name="Warfarin with supratherapeutic INR",
        severity="amber",
        required_classes=(("vka",),),
        context_condition=ContextCondition(
            description="INR >= 4", lab="INR", lab_gte=4.0,
        ),
        mechanism=(
            "An INR above 4 on a vitamin K antagonist sharply increases "
            "major bleeding risk, usually from a drug interaction or dosing "
            "error."
        ),
        recommendation=(
            "Hold warfarin and review for interacting drugs; recheck INR "
            "and assess for bleeding / vitamin K per protocol."
        ),
        citation="ACCP/CHEST antithrombotic guidelines (VKA management)",
    ),
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _scan_supplemental(note: str) -> List[Finding]:
    """Scan the note for SUPPLEMENTAL_MEDICATIONS using the same
    word-boundary, case-insensitive style as the extractor's med scan."""
    out: List[Finding] = []
    lower = note.lower()
    for med, klass in SUPPLEMENTAL_MEDICATIONS.items():
        for m in re.finditer(rf"\b{re.escape(med)}\b", lower):
            out.append(
                Finding(
                    kind="med",
                    label=med,
                    value=None,
                    evidence=Span(m.start(), m.end(), note[m.start():m.end()]),
                    metadata={"class": klass},
                )
            )
    # Supplemental (brand-name / extra-class) meds must get the SAME NegEx-lite
    # negation treatment the extractor applies to its own med scan — otherwise
    # "Eliquis held" or "tramadol discontinued" would fire interaction flags
    # while the generic-name equivalent ("apixaban held") correctly does not.
    return _tag_negation(note, out)


def _active_meds(ext: ExtractionResult, note: str) -> Dict[str, Finding]:
    """Deduplicated map of canonical drug name -> first supporting finding.

    Skips findings the extractor marked negated; canonicalizes brand names
    so one drug can never satisfy a two-distinct-drug rule by itself.
    """
    meds: Dict[str, Finding] = {}
    for f in list(ext.meds) + _scan_supplemental(note):
        if f.metadata.get("negated"):
            continue
        canonical = ALIASES.get(f.label, f.label)
        meds.setdefault(canonical, f)
    return meds


def _assign_distinct(
    groups: Tuple[Tuple[str, ...], ...],
    meds: Dict[str, Finding],
) -> Optional[List[Tuple[str, Finding]]]:
    """Backtracking assignment of DISTINCT meds to class groups.

    Returns one (name, finding) per group, or None if no assignment exists.
    """

    def _matches(finding: Finding, group: Tuple[str, ...]) -> bool:
        klass = finding.metadata.get("class", "")
        return any(sub in klass for sub in group)

    def _recurse(i: int, used: frozenset) -> Optional[List[Tuple[str, Finding]]]:
        if i == len(groups):
            return []
        for name, finding in meds.items():
            if name in used or not _matches(finding, groups[i]):
                continue
            rest = _recurse(i + 1, used | {name})
            if rest is not None:
                return [(name, finding)] + rest
        return None

    return _recurse(0, frozenset())


def _context_satisfied(
    cond: Optional[ContextCondition], ext: ExtractionResult
) -> Tuple[bool, List[Span]]:
    """Evaluate a declarative context condition against non-negated labs and
    symptoms. Returns (satisfied, evidence spans)."""
    if cond is None:
        return True, []
    evidence: List[Span] = []
    if cond.lab and (cond.lab_gte is not None or cond.lab_lte is not None):
        for lab in ext.labs:
            if lab.metadata.get("negated") or lab.label != cond.lab or not lab.value:
                continue
            try:
                value = float(lab.value)
            except ValueError:
                continue
            if cond.lab_gte is not None and value >= cond.lab_gte:
                evidence.append(lab.evidence)
                break
            if cond.lab_lte is not None and value <= cond.lab_lte:
                evidence.append(lab.evidence)
                break
    if cond.symptom:
        for sym in ext.symptoms:
            if sym.metadata.get("negated"):
                continue
            if sym.label == cond.symptom:
                evidence.append(sym.evidence)
                break
    return bool(evidence), evidence


def screen(ext: ExtractionResult, note: str) -> List[InteractionFlag]:
    """Run the full rule table against one note's extraction.

    Returns flags sorted red-first (then rule-table order), each carrying
    the meds involved, the context evidence, and the rule's recommendation
    and citation — everything the pharmacist queue needs to act.
    """
    meds = _active_meds(ext, note)
    flagged: List[Tuple[int, int, InteractionFlag]] = []
    for idx, rule in enumerate(RULES):
        assignment = _assign_distinct(rule.required_classes, meds)
        if assignment is None:
            continue
        satisfied, context_evidence = _context_satisfied(rule.context_condition, ext)
        if not satisfied:
            continue
        flag = InteractionFlag(
            rule_key=rule.key,
            name=rule.name,
            severity=rule.severity,
            mechanism=rule.mechanism,
            recommendation=rule.recommendation,
            citation=rule.citation,
            meds_involved=[
                MedInvolved(
                    name=name,
                    drug_class=finding.metadata.get("class", ""),
                    evidence=finding.evidence,
                )
                for name, finding in assignment
            ],
            context_evidence=context_evidence,
        )
        flagged.append((SEVERITY_RANK.get(rule.severity, 9), idx, flag))

    flagged.sort(key=lambda item: (item[0], item[1]))
    return [flag for _, _, flag in flagged]
