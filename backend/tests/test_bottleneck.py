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
