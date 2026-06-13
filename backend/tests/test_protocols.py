"""Protocol library / silent-failure tests.

Verifies that the protocol matcher fires when it should, doesn't fire when
the trigger is negated or historical, and produces silent failures only
when expected steps aren't documented.
"""

import re

from app.protocols.library import PROTOCOLS, by_key
from app.services.silent_failure import evaluate, silent_failures


def test_protocol_library_loads():
    assert len(PROTOCOLS) == 12
    keys = {p.key for p in PROTOCOLS}
    assert {"sepsis", "acs", "stroke", "cap", "dka", "pe", "gi_bleed",
            "aki", "ciwa", "neutropenic_fever", "hyperkalemia", "copd"} == keys


def test_each_protocol_has_expected_actions():
    for p in PROTOCOLS:
        assert len(p.expected_actions) >= 3, f"{p.key} should have >=3 expected actions"
        assert p.citation
        assert p.owner
        assert p.urgency_if_incomplete in {"red", "amber", "green"}


def test_by_key_lookup():
    assert by_key("sepsis").name == "Surviving Sepsis Hour-1 Bundle"
    assert by_key("notreal") is None


def test_sepsis_fires_and_finds_gap():
    note = (
        "72yo with fever 39.4, BP 88/52, lactate 3.1. WBC 18. "
        "Meets SIRS criteria. IV fluids initiated."
    )
    matches = evaluate(note)
    sepsis_match = next(m for m in matches if m.protocol.key == "sepsis")
    assert sepsis_match.triggered

    sfs = silent_failures(note)
    sf_keys = {sf.protocol_key for sf in sfs}
    assert "sepsis" in sf_keys
    # antibiotics + blood cultures not documented; lactate + fluids are
    sepsis_misses = [sf.missing_action for sf in sfs if sf.protocol_key == "sepsis"]
    assert any("antibiotics" in m.lower() for m in sepsis_misses)


def test_sepsis_does_not_fire_when_resolved():
    note = (
        "Hospital day 6. Sepsis resolved with antibiotics. Afebrile for 72h. "
        "WBC normalized at 7.4."
    )
    matches = evaluate(note)
    sepsis_match = next(m for m in matches if m.protocol.key == "sepsis")
    assert not sepsis_match.triggered


def test_dka_full_bundle_no_gap():
    note = (
        "22yo T1DM with DKA, glucose 512, anion gap 24. "
        "Insulin drip initiated at 0.1 units/kg. IV fluids running, normal saline bolus. "
        "Potassium repletion with KCl. Repeat labs in 2h to trend gap."
    )
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "dka"]
    assert sfs == [], f"unexpected DKA gaps: {[s.missing_action for s in sfs]}"


def test_ambiguous_cva_does_not_fire_without_context():
    """'CVA' can mean costovertebral angle. Don't fire stroke protocol on it."""
    note = (
        "Right flank pain, mild CVA tenderness on exam. "
        "UA pending. No focal neuro deficits."
    )
    matches = evaluate(note)
    stroke_match = next(m for m in matches if m.protocol.key == "stroke")
    assert not stroke_match.triggered


def test_cva_fires_when_corroborated():
    note = (
        "78yo female, last known well 90 min ago. CVA suspected. "
        "NIHSS 14. Right hemiparesis, aphasia. Head CT pending."
    )
    matches = evaluate(note)
    stroke_match = next(m for m in matches if m.protocol.key == "stroke")
    assert stroke_match.triggered


def test_hyperkalemia_triggers_at_high_k():
    note = "ESRD patient missed HD. Labs: K 6.8, Cr 8.2. Peaked T-waves on ECG."
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "hyperkalemia"]
    # ECG documented, peaked T-waves mentioned, so ECG action is ok
    miss_labels = {sf.missing_action for sf in sfs}
    assert any("calcium" in m.lower() for m in miss_labels) or len(miss_labels) > 0


def test_neutropenic_fever_fires():
    note = "AML patient day 9 chemo, fever 38.6, ANC 180. Blood cultures x2 drawn."
    matches = evaluate(note)
    nf = next(m for m in matches if m.protocol.key == "neutropenic_fever")
    assert nf.triggered


def test_pe_fires_with_confirmation():
    note = "Post-op day 10 with pleuritic chest pain, D-dimer 4.8. CT-PA confirms PE."
    matches = evaluate(note)
    pe = next(m for m in matches if m.protocol.key == "pe")
    assert pe.triggered


def test_gi_bleed_fires_on_melena():
    note = "Patient on apixaban with melena x 2 days, hgb dropped from 12 to 8.4."
    matches = evaluate(note)
    gib = next(m for m in matches if m.protocol.key == "gi_bleed")
    assert gib.triggered


def test_copd_exacerbation_fires():
    note = "Patient with COPD exacerbation, increased sputum, started DuoNeb. CXR clear."
    matches = evaluate(note)
    copd = next(m for m in matches if m.protocol.key == "copd")
    assert copd.triggered


def test_every_pattern_compiles_and_has_no_double_word_boundary():
    """Every trigger and documented pattern across all 12 protocols must be a
    valid regex and free of the `\\b\\b` double-word-boundary typo class."""
    assert len(PROTOCOLS) == 12
    for p in PROTOCOLS:
        for pat in p.triggers:
            re.compile(pat)
            assert r"\b\b" not in pat, f"{p.key} trigger has double \\b: {pat!r}"
        for action in p.expected_actions:
            for pat in action.documented_patterns:
                re.compile(pat)
                assert r"\b\b" not in pat, (
                    f"{p.key}.{action.key} documented pattern has double \\b: {pat!r}"
                )


def test_cap_trigger_fires_on_abbreviation():
    """Regression for the `\\bCAP\\b\\b` typo in the CAP trigger."""
    note = "65yo with CAP, RLL infiltrate on CXR. Ceftriaxone and azithromycin started."
    matches = evaluate(note)
    cap = next(m for m in matches if m.protocol.key == "cap")
    assert cap.triggered


def test_dka_k_measurement_is_not_repletion():
    """A bare K lab value ("K 5.4") must not satisfy the potassium-repletion
    step — only repletion language or a KCl order counts."""
    note = (
        "26yo T1DM with DKA, glucose 480, anion gap 22, K 5.4. "
        "Insulin drip started. IV fluids running. Repeat labs q2h."
    )
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "dka"]
    assert any("potassium" in sf.missing_action.lower() for sf in sfs), \
        f"K measurement alone should leave repletion missing, got {[s.missing_action for s in sfs]}"


def test_dka_kcl_order_still_counts_as_repletion():
    note = (
        "26yo T1DM with DKA, glucose 480, anion gap 22. Insulin drip started. "
        "IV fluids running. KCl 20 mEq added to fluids. Repeat labs q2h."
    )
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "dka"]
    assert not any("potassium" in sf.missing_action.lower() for sf in sfs)


def test_hyperkalemia_hospital_day_is_not_dialysis():
    """`HD 3` (hospital day) must not satisfy the removal step."""
    note = (
        "HD 3 for cellulitis. K 6.7 this morning with peaked T-waves on ECG. "
        "Calcium gluconate given. Insulin and D50 administered."
    )
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "hyperkalemia"]
    assert any("removal" in sf.missing_action.lower() for sf in sfs), \
        f"'HD 3' should not count as dialysis, got misses: {[s.missing_action for s in sfs]}"


def test_hyperkalemia_dialysis_plan_still_counts():
    note = (
        "ESRD with K 6.7, peaked T-waves on ECG. Calcium gluconate given. "
        "Insulin and D50 administered. Urgent HD arranged with nephrology."
    )
    sfs = [sf for sf in silent_failures(note) if sf.protocol_key == "hyperkalemia"]
    assert not any("removal" in sf.missing_action.lower() for sf in sfs)


def test_sirs_trigger_not_negated_by_following_sentence():
    """Regression: trigger negation must scan LEFT context only. 'No
    antibiotics given yet' AFTER the trigger is a gap, not a negation —
    it used to suppress the SIRS trigger entirely."""
    note = "72yo, fever 39.2, HR 122. Meets SIRS criteria. No antibiotics given yet."
    matches = evaluate(note)
    sepsis = next(m for m in matches if m.protocol.key == "sepsis")
    assert sepsis.triggered
    assert any("antibiotics" in a.label.lower() for a in sepsis.missing)


def test_negation_cue_does_not_leak_across_sentence_boundary():
    """'CXR no infiltrate.' in the previous sentence must not suppress the
    COPD-exacerbation trigger in the assessment line."""
    note = (
        "Imaging: CXR no infiltrate.\n"
        "Assessment: COPD exacerbation, moderate.\n"
        "Plan: DuoNeb started. Azithromycin started."
    )
    matches = evaluate(note)
    copd = next(m for m in matches if m.protocol.key == "copd")
    assert copd.triggered
    assert any(a.key == "steroids" for a in copd.missing)


def test_historical_cue_after_trigger_still_suppresses():
    """Historical context legitimately follows the trigger ('stroke 5 days
    ago') and must keep suppressing within the same sentence."""
    note = "73yo male, stroke 5 days ago. Deficits improving but residual."
    matches = evaluate(note)
    stroke = next(m for m in matches if m.protocol.key == "stroke")
    assert not stroke.triggered


def test_stroke_window_expired_is_resolution():
    """A dispo-phase note ('Stroke window expired') no longer owes the
    acute tPA bundle."""
    note = (
        "Assessment: ischemic stroke, residual deficits. Stroke window expired. "
        "Plan: awaiting bed at rehab facility."
    )
    matches = evaluate(note)
    stroke = next(m for m in matches if m.protocol.key == "stroke")
    assert not stroke.triggered


def test_acs_rule_out_language_suppresses_protocol():
    """Serial negative troponins / explicit rule-out conclude the ACS
    pathway — the bundle is not 'incomplete'."""
    note = (
        "49yo male with atypical chest pain, fully ruled out with two negative "
        "troponins and normal stress test. Labs: troponin x 2 negative."
    )
    matches = evaluate(note)
    acs = next(m for m in matches if m.protocol.key == "acs")
    assert not acs.triggered


def test_aki_mild_bump_does_not_owe_full_workup_bundle():
    """KDIGO gate: 'developing AKI' at Cr 1.7 with preserved urine output is
    nephrotoxin-review territory, not a full-workup-bundle gap."""
    note = (
        "Developing AKI, likely multifactorial. Creatinine has risen from "
        "1.0 to 1.7. Plan: continue current antibiotics."
    )
    matches = evaluate(note)
    aki = next(m for m in matches if m.protocol.key == "aki")
    assert not aki.triggered


def test_aki_established_severity_fires_workup_bundle():
    note = (
        "Assessment: acute kidney injury. Creatinine rising from baseline "
        "1.0 to 2.4 over 36h. UOP <300 mL/24h."
    )
    matches = evaluate(note)
    aki = next(m for m in matches if m.protocol.key == "aki")
    assert aki.triggered


def test_aki_held_nephrotoxin_counts_as_med_review():
    """'Held vancomycin' is a completed nephrotoxin review — aminoglycosides
    and vancomycin are nephrotoxins just like NSAIDs."""
    note = (
        "Assessment: AKI, likely ATN. Creatinine rising from 1.1 to 3.4. "
        "UOP <300 mL/24h. Euvolemic. Urine sediment with muddy brown casts. "
        "Renal US no hydronephrosis. Plan: held vancomycin."
    )
    matches = evaluate(note)
    aki = next(m for m in matches if m.protocol.key == "aki")
    assert aki.triggered
    assert not any(a.key == "med_review" for a in aki.missing)


def test_sepsis_moderate_lactate_alone_does_not_fire_bundle():
    """Lactate 2.8 in a surgical abdomen without any sepsis language does
    not by itself owe the hour-1 bundle."""
    note = (
        "58yo with sudden severe abdominal pain, rigid abdomen. "
        "Labs: WBC 16.4, lactate 2.8. Plan: NPO, IVF, broad-spectrum antibiotics."
    )
    matches = evaluate(note)
    sepsis = next(m for m in matches if m.protocol.key == "sepsis")
    assert not sepsis.triggered


def test_sepsis_shock_threshold_lactate_fires_bundle():
    note = "Found down, ill-appearing. Labs: lactate 4.8."
    matches = evaluate(note)
    sepsis = next(m for m in matches if m.protocol.key == "sepsis")
    assert sepsis.triggered


def test_silent_failures_accepts_precomputed_matches():
    """Passing evaluate()'s output in must yield identical results to letting
    silent_failures compute it (the classifier threads matches through)."""
    note = (
        "72yo with fever 39.4, BP 88/52, lactate 3.1. WBC 18. "
        "Meets SIRS criteria. IV fluids initiated."
    )
    matches = evaluate(note)
    assert silent_failures(note, matches) == silent_failures(note)
    assert silent_failures(note, matches=matches) == silent_failures(note)
