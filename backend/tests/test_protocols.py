"""Protocol library / silent-failure tests.

Verifies that the protocol matcher fires when it should, doesn't fire when
the trigger is negated or historical, and produces silent failures only
when expected steps aren't documented.
"""

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
