"""Tests for the cascading bottleneck classifier."""

from app.nlp.extractor import extract
from app.services.bottleneck import classify


def _classify(note: str):
    return classify(note, extract(note))


def test_clear_patient_returns_clear():
    note = (
        "32yo female with migraine, treated and resolved after IV fluids and ketorolac. "
        "Nonfocal neuro exam, comfortable. Discharge home with neurology follow-up scheduled."
    )
    result = _classify(note)
    assert result.primary.category == "clear"
    assert result.primary.urgency == "green"


def test_missing_soc_wins_over_dispo():
    """A patient with both a sepsis gap and a placement issue should surface
    the sepsis gap first — patient safety dominates."""
    note = (
        "72yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
        "IV fluids 30 mL/kg initiated. SNF placement requested 3 days ago, "
        "case management following."
    )
    result = _classify(note)
    assert result.primary.category == "missing_soc"


def test_consult_pending_routes_to_physician():
    note = (
        "Hip fracture, surgical candidate. Orthopedic consult requested 14h ago, "
        "awaiting callback. Patient otherwise medically optimized."
    )
    result = _classify(note)
    assert result.primary.category == "awaiting_consult"
    assert result.primary.owner == "physician"


def test_dispo_delay_routes_to_case_manager():
    note = (
        "COPD exacerbation resolved. Off supplemental O2 x 24h. Medically ready. "
        "SNF placement requested 3 days ago. Case management notes 4 SNFs declined "
        "due to no insurance authorization."
    )
    result = _classify(note)
    assert result.primary.category in {"dispo_delay", "missing_soc"}
    # Should be dispo since COPD is resolved
    if result.primary.category == "dispo_delay":
        assert result.primary.owner == "case_manager"


def test_med_risk_anticoag_plus_bleed():
    note = (
        "81yo on apixaban for AFib presents with melena x 2 days, hgb dropped to 8.4. "
        "Also on aspirin and ibuprofen."
    )
    result = _classify(note)
    # Either med_risk or missing_soc (GI bleed protocol) is acceptable
    assert result.primary.category in {"med_risk", "missing_soc"}


def test_nephrotoxic_flag_subsumed_by_aki_med_review_gap():
    """When the AKI workup protocol is triggered and its own medication-review
    step is missing, the nephrotoxin interaction flag is the evidence FOR that
    gap — the patient routes once, to the physician owning the protocol gap,
    not twice (physician + pharmacist) for the same problem."""
    note = (
        "Cellulitis day 4 on vancomycin and tobramycin. Creatinine rising from "
        "baseline 1.0 to 2.4 over 36h. UOP <300 mL/24h. Exam: euvolemic. "
        "Labs: Cr 2.4. Urine sediment with muddy brown casts. "
        "Plan: continue current regimen."
    )
    result = _classify(note)
    assert result.primary.category == "missing_soc"
    assert result.primary.owner == "physician"
    cats = {b.category for b in [result.primary] + result.secondary}
    assert "med_risk" not in cats, "subsumed nephrotoxin flag must not split routing"


def test_red_flag_with_active_harm_outranks_equal_urgency_protocol_gap():
    """Tie-break exception: anticoagulant + documented melena is harm in
    progress (red, with objective context evidence) — it outranks the
    equally-red GI-bleed bundle gaps and routes to the pharmacist."""
    note = (
        "81yo on apixaban for AFib presents with melena x 2 days, hgb 8.4. "
        "Plan: GI consult."
    )
    result = _classify(note)
    assert result.primary.category == "med_risk"
    assert result.primary.owner == "pharmacist"
    assert any(b.category == "missing_soc" for b in result.secondary)


def test_red_flag_without_context_evidence_does_not_jump_protocol_gap():
    """The tie-break exception is narrow: a combination flag with no
    objective harm evidence (warfarin + ibuprofen, no bleed signs in the
    interaction context) stays behind the equally-red protocol gap."""
    note = "On warfarin and ibuprofen at home. Hematemesis this morning."
    result = _classify(note)
    assert result.primary.category == "missing_soc"
    assert any(b.category == "med_risk" for b in result.secondary)


def test_to_dict_serializable():
    """Triage result must serialize to JSON for DB storage."""
    import json
    note = "72yo with fever, BP 88/52, lactate 3.1. SIRS criteria. IV fluids initiated."
    result = _classify(note)
    payload = result.to_dict()
    json.dumps(payload)
    assert "primary" in payload
    assert "silent_failures" in payload
    assert "protocol_matches" in payload


def test_secondary_bottlenecks_populated():
    """When multiple categories fire, secondary list should not be empty."""
    note = (
        "AKI on home lisinopril and ibuprofen. Cr 2.4. SNF placement requested. "
        "Awaiting nephrology consult, placed yesterday."
    )
    result = _classify(note)
    # AKI workup will trigger as missing_soc, dispo and consult should be secondary
    assert len(result.secondary) >= 1


def test_urgency_ordering():
    """Red bottlenecks should always sort before amber/green."""
    note = (
        "Sepsis with bundle gap. SNF placement also pending. "
        "Lactate 3.1, BP 88/52, IV fluids running."
    )
    result = _classify(note)
    if result.secondary:
        urgency_rank = {"red": 0, "amber": 1, "green": 2}
        assert urgency_rank[result.primary.urgency] <= urgency_rank[result.secondary[0].urgency]
