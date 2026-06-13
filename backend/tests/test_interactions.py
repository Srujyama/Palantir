"""Tests for the data-encoded drug-interaction screening engine.

Covers each rule family (fire + non-fire), the negated-finding contract,
sorting, the API endpoint, and that med_risk still wins in the bottleneck
cascade where it used to.
"""

from __future__ import annotations

import pytest

from app.nlp.extractor import extract
from app.services.bottleneck import classify
from app.services.interactions import screen
from tests.conftest import build_test_client, teardown_test_client


def _screen(note: str):
    return screen(extract(note), note)


def _keys(flags):
    return {f.rule_key for f in flags}


# ---------------------------------------------------------------------------
# Rule families: fire + non-fire
# ---------------------------------------------------------------------------

def test_nephrotoxic_combo_fires_with_high_creatinine():
    flags = _screen("On ibuprofen and tobramycin. Creatinine 2.1 this AM.")
    assert "nephrotoxic_combo_aki" in _keys(flags)
    flag = next(f for f in flags if f.rule_key == "nephrotoxic_combo_aki")
    assert flag.severity == "red"
    assert flag.context_evidence, "creatinine span should be cited"
    assert any("nephrotox" in m.drug_class for m in flag.meds_involved)


def test_nephrotoxic_combo_silent_with_normal_creatinine():
    flags = _screen("On ibuprofen for knee pain. Creatinine 1.0.")
    assert "nephrotoxic_combo_aki" not in _keys(flags)


def test_qt_stack_two_agents_is_amber():
    flags = _screen("Started azithromycin; ondansetron PRN for nausea.")
    flag = next(f for f in flags if f.rule_key == "qt_stack")
    assert flag.severity == "amber"
    assert {m.name for m in flag.meds_involved} == {"azithromycin", "ondansetron"}


def test_qt_single_agent_with_long_qtc_is_red():
    flags = _screen("On azithromycin. ECG shows QTc 512 ms.")
    assert "qt_prolonged_qtc" in _keys(flags)
    assert next(f for f in flags if f.rule_key == "qt_prolonged_qtc").severity == "red"
    # Only one QT agent, so the two-agent stack must NOT fire.
    assert "qt_stack" not in _keys(flags)


def test_qt_single_agent_without_qtc_is_silent():
    flags = _screen("On azithromycin for CAP, day 2.")
    assert "qt_prolonged_qtc" not in _keys(flags)
    assert "qt_stack" not in _keys(flags)


def test_anticoag_plus_melena_is_red():
    flags = _screen("81yo on apixaban for AFib presents with melena x 2 days.")
    flag = next(f for f in flags if f.rule_key == "anticoag_active_bleed")
    assert flag.severity == "red"
    assert flag.context_evidence and "melena" in flag.context_evidence[0].text.lower()


def test_anticoag_plus_nsaid_is_red():
    flags = _screen("On warfarin at home; taking naproxen for back pain.")
    assert "anticoag_nsaid" in _keys(flags)


def test_anticoag_alone_is_silent():
    flags = _screen("On apixaban for AFib, therapeutic, no complaints.")
    assert not any(
        k in _keys(flags)
        for k in ("anticoag_active_bleed", "anticoag_nsaid", "dual_anticoagulation")
    )


def test_dual_anticoagulation_is_red():
    flags = _screen("Med rec: warfarin nightly plus enoxaparin BID.")
    assert "dual_anticoagulation" in _keys(flags)


def test_brand_generic_alias_does_not_double_count():
    """enoxaparin (Lovenox) is one drug — must not fire dual anticoagulation."""
    flags = _screen("Continue enoxaparin (lovenox) 40 mg daily.")
    assert "dual_anticoagulation" not in _keys(flags)


def test_doac_antiplatelet_is_amber():
    flags = _screen("Home meds: apixaban and aspirin 81 mg daily.")
    flag = next(f for f in flags if f.rule_key == "doac_antiplatelet")
    assert flag.severity == "amber"


def test_triple_whammy_fires_with_all_three():
    flags = _screen("Home meds: lisinopril, furosemide, and ibuprofen PRN.")
    assert "triple_whammy" in _keys(flags)


def test_triple_whammy_silent_with_only_two():
    flags = _screen("Home meds: lisinopril and furosemide.")
    assert "triple_whammy" not in _keys(flags)


def test_k_retainer_with_hyperkalemia_is_red():
    flags = _screen("On spironolactone. Labs notable for K 5.8.")
    flag = next(f for f in flags if f.rule_key == "hyperkalemia_k_retainers")
    assert flag.severity == "red"


def test_k_retainer_with_normal_k_is_silent():
    flags = _screen("On spironolactone. Labs notable for K 4.2.")
    assert "hyperkalemia_k_retainers" not in _keys(flags)


def test_opioid_benzo_stack_is_amber():
    flags = _screen("Receiving oxycodone q4h and lorazepam PRN anxiety.")
    assert "opioid_benzo_stack" in _keys(flags)


def test_opioid_alone_is_silent():
    flags = _screen("Receiving oxycodone q4h for pain.")
    assert "opioid_benzo_stack" not in _keys(flags)


def test_serotonergic_stack_with_supplemental_med():
    """tramadol comes from SUPPLEMENTAL_MEDICATIONS, citalopram from the
    extractor — the engine must merge both surfaces."""
    flags = _screen("Home meds include citalopram; started tramadol for pain.")
    flag = next(f for f in flags if f.rule_key == "serotonergic_stack")
    assert flag.severity == "amber"
    assert {m.name for m in flag.meds_involved} == {"citalopram", "tramadol"}


def test_serotonergic_single_agent_is_silent():
    flags = _screen("Home meds include citalopram, stable dose.")
    assert "serotonergic_stack" not in _keys(flags)


def test_insulin_with_hypoglycemia_is_amber():
    flags = _screen(
        "Continued home insulin regimen. Overnight glucose 42, treated with D50."
    )
    flag = next(f for f in flags if f.rule_key == "insulin_hypoglycemia")
    assert flag.severity == "amber"
    assert flag.context_evidence, "the hypoglycemic glucose span should be cited"


def test_insulin_with_normal_glucose_is_silent():
    flags = _screen("Home insulin continued. Glucose 156 this morning.")
    assert "insulin_hypoglycemia" not in _keys(flags)


def test_warfarin_supratherapeutic_inr_fires():
    flags = _screen("Started on warfarin for AFib. Labs: INR 4.6 (target 2-3).")
    flag = next(f for f in flags if f.rule_key == "warfarin_supratherapeutic_inr")
    assert flag.severity == "amber"
    assert flag.context_evidence


def test_warfarin_therapeutic_inr_is_silent():
    flags = _screen("On warfarin, INR 2.4, therapeutic.")
    assert "warfarin_supratherapeutic_inr" not in _keys(flags)


# ---------------------------------------------------------------------------
# Flag contract: sorting, citations, serialization
# ---------------------------------------------------------------------------

def test_red_flags_sort_before_amber():
    note = (
        "On apixaban, presenting with melena. Also receiving oxycodone "
        "and lorazepam overnight."
    )
    flags = _screen(note)
    severities = [f.severity for f in flags]
    assert severities == sorted(severities, key=lambda s: {"red": 0, "amber": 1}[s])
    assert flags[0].severity == "red"


def test_every_flag_carries_citation_and_recommendation():
    note = (
        "On apixaban and aspirin with melena. Lisinopril, furosemide, "
        "ibuprofen on board. Creatinine 2.0. Oxycodone plus lorazepam."
    )
    for f in _screen(note):
        assert f.citation
        assert f.recommendation
        assert f.mechanism
        assert f.meds_involved
        d = f.to_dict()
        assert d["meds_involved"][0].keys() >= {"name", "class", "evidence"}


# ---------------------------------------------------------------------------
# Negation contract
# ---------------------------------------------------------------------------

def test_negated_med_findings_are_skipped():
    """Engine contract: findings carrying metadata negated=True are ignored,
    regardless of when the extractor's negation upgrade lands."""
    note = "Not on azithromycin. Ondansetron PRN."
    ext = extract(note)
    for m in ext.meds:
        if m.label == "azithromycin":
            m.metadata["negated"] = True
    flags = screen(ext, note)
    assert "qt_stack" not in _keys(flags)


def test_negated_context_lab_is_skipped():
    note = "On ibuprofen. Creatinine 2.1 (prior admission)."
    ext = extract(note)
    for lab in ext.labs:
        if lab.label == "creatinine":
            lab.metadata["negated"] = True
    flags = screen(ext, note)
    assert "nephrotoxic_combo_aki" not in _keys(flags)


def test_denied_melena_suppressed_once_extractor_negation_lands():
    """Tolerant: only asserts suppression once the extractor actually emits
    negated metadata for 'denies melena'."""
    note = "On apixaban for AFib. Denies melena or hematemesis."
    ext = extract(note)
    melena = [s for s in ext.symptoms if s.label == "melena"]
    if not any(s.metadata.get("negated") for s in melena):
        pytest.skip("extractor negation metadata not yet landed")
    flags = screen(ext, note)
    assert "anticoag_active_bleed" not in _keys(flags)


# ---------------------------------------------------------------------------
# Cascade integration: med_risk still wins where it used to
# ---------------------------------------------------------------------------

def test_cascade_qt_red_becomes_primary_med_risk():
    note = "Floor patient, comfortable. Meds: azithromycin, ondansetron. QTc 512 ms."
    result = classify(note, extract(note))
    assert result.primary.category == "med_risk"
    assert result.primary.urgency == "red"
    assert result.primary.owner == "pharmacist"
    assert result.primary.citation == "CredibleMeds QT drug list"
    assert result.primary.evidence


def test_cascade_nephrotoxic_red_becomes_primary_med_risk():
    note = "On ibuprofen and tobramycin. Creatinine 2.1."
    result = classify(note, extract(note))
    assert result.primary.category == "med_risk"
    assert result.primary.urgency == "red"
    assert result.primary.owner == "pharmacist"


def test_cascade_anticoag_bleed_preserved():
    """Same shape as the legacy bottleneck test: med_risk or missing_soc
    (GI-bleed protocol) wins, and a red pharmacist med_risk is present."""
    note = (
        "81yo on apixaban for AFib presents with melena x 2 days, hgb dropped "
        "to 8.4. Also on aspirin and ibuprofen."
    )
    result = classify(note, extract(note))
    assert result.primary.category in {"med_risk", "missing_soc"}
    med = [b for b in [result.primary] + result.secondary if b.category == "med_risk"]
    assert med and med[0].urgency == "red" and med[0].owner == "pharmacist"


def test_cascade_qt_stack_amber_preserved():
    note = "Stable overnight. Receiving azithromycin and ondansetron."
    result = classify(note, extract(note))
    med = [b for b in [result.primary] + result.secondary if b.category == "med_risk"]
    assert med and med[0].urgency == "amber" and med[0].owner == "pharmacist"


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def _ensure_router_mounted():
    """The integrator owns app/main.py; mount our router here if it has not
    been registered yet so the endpoint is testable either way."""
    from app.main import app
    from app.api.interactions import router

    mounted = any(
        getattr(r, "path", "").endswith("/{patient_id}/interactions")
        for r in app.routes
    )
    if not mounted:
        app.include_router(router)


def test_interactions_endpoint_returns_flags():
    _ensure_router_mounted()
    client, _ = build_test_client(
        seed_patients=[
            {
                "id": "P-IX01",
                "note_text": (
                    "81yo on apixaban for AFib with melena x 2 days. "
                    "Also on aspirin."
                ),
            }
        ]
    )
    try:
        resp = client.get("/patients/P-IX01/interactions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["patient_id"] == "P-IX01"
        assert body["flags"], "expected at least one interaction flag"
        first = body["flags"][0]
        assert first["severity"] == "red"
        assert {"rule_key", "name", "severity", "mechanism", "recommendation",
                "citation", "meds_involved", "context_evidence"} <= first.keys()
        med = first["meds_involved"][0]
        assert {"name", "class", "evidence"} <= med.keys()
        assert {"start", "end", "text"} <= med["evidence"].keys()
    finally:
        teardown_test_client()


def test_interactions_endpoint_404_on_missing_patient():
    _ensure_router_mounted()
    client, _ = build_test_client(seed_patients=[])
    try:
        resp = client.get("/patients/P-NOPE/interactions")
        assert resp.status_code == 404
    finally:
        teardown_test_client()


# ---------------------------------------------------------------------------
# Regression: supplemental / brand-name meds must inherit negation tagging
# (adversarial-review finding — held brand-name DOAC was firing red flags)
# ---------------------------------------------------------------------------

def test_held_brand_doac_with_melena_does_not_fire_red():
    """'Eliquis held' + melena must NOT produce anticoag_active_bleed — the
    generic-name equivalent ('apixaban held') already does not."""
    note = "Pt with melena overnight. Eliquis held this morning pending GI eval."
    assert "anticoag_active_bleed" not in _keys(_screen(note))
    # Sanity: the un-held brand name DOES fire, so the rule still works.
    active = "Pt with melena overnight. On Eliquis at home, continued."
    assert "anticoag_active_bleed" in _keys(_screen(active))


def test_held_supplemental_serotonergics_do_not_stack():
    note = "Tramadol held on admission. Sertraline discontinued by psychiatry."
    assert "serotonergic_stack" not in _keys(_screen(note))
