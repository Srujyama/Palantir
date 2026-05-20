"""Tests for the clinical NLP extractor."""

from app.nlp.extractor import extract


def test_extracts_vitals():
    note = "BP 88/52, HR 122, RR 24, SpO2 91%. Fever to 39.4."
    ext = extract(note)
    labels = {v.label for v in ext.vitals}
    assert {"BP", "HR", "RR", "SpO2", "Temp"}.issubset(labels)


def test_extracts_labs():
    note = "WBC 18.2, lactate 3.1, creatinine 1.9, K 5.4, ANC 180, pH 7.18, bicarb 9."
    ext = extract(note)
    labels = {l.label for l in ext.labs}
    assert "WBC" in labels
    assert "lactate" in labels
    assert "creatinine" in labels
    assert "potassium" in labels
    assert "ANC" in labels
    assert "ph" in labels
    assert "bicarbonate" in labels


def test_extracts_medications_with_class():
    note = "Started vancomycin and zosyn. Home meds: lisinopril, ibuprofen, apixaban."
    ext = extract(note)
    med_classes = {m.label: m.metadata.get("class") for m in ext.meds}
    assert "vancomycin" in med_classes
    assert "anticoag" in med_classes["apixaban"]
    assert "nephrotox" in med_classes["ibuprofen"]


def test_extracts_consults_pending():
    note = "Orthopedic consult requested 14h ago, awaiting callback."
    ext = extract(note)
    assert any(c.label == "orthopedics" and c.value == "pending" for c in ext.consults)


def test_extracts_imaging_pending():
    note = "CT abd ordered 5h ago, still in queue per radiology."
    ext = extract(note)
    pending_ct = [i for i in ext.imaging if i.label == "ct" and i.value == "pending"]
    assert pending_ct


def test_extracts_dispo_blockers():
    note = (
        "Medically ready for discharge. SNF placement requested 3 days ago. "
        "4 SNFs declined due to no insurance authorization."
    )
    ext = extract(note)
    labels = {d.label for d in ext.dispo}
    assert "snf_placement" in labels
    assert "insurance_auth" in labels
    assert "medically_ready" in labels


def test_extracts_code_status_and_mobility():
    note = "Code status: DNR / DNI. Patient walks with walker. Fall risk."
    ext = extract(note)
    cs_labels = {c.label for c in ext.code_status}
    mob_labels = {m.label for m in ext.mobility}
    assert "dnr" in cs_labels
    assert "dni" in cs_labels
    assert "walks_with_assist" in mob_labels
    assert "fall_risk" in mob_labels


def test_extracts_social_context():
    note = (
        "Lives alone with limited mobility. Mandarin-speaking only. "
        "No family support."
    )
    ext = extract(note)
    soc = {s.label for s in ext.social}
    assert "lives_alone" in soc
    assert "language_barrier" in soc
    assert "family_support_limited" in soc


def test_extracts_risk_factors():
    note = "Third DKA admission in 8 months. Running out of insulin again. Intermittent housing."
    ext = extract(note)
    assert len(ext.risk_factors) >= 2


def test_to_dict_serializable():
    """Extraction result must be JSON-friendly for storage in DB.JSON column."""
    import json
    ext = extract("WBC 12, BP 100/60. Vancomycin started.")
    payload = ext.to_dict()
    json.dumps(payload)
    assert "vitals" in payload
    assert "code_status" in payload
