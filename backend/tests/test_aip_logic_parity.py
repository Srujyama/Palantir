"""Parity gate for the Foundry Functions artifact.

`foundry_export/aip_logic_classify_bottleneck.py` claims to be a complete,
self-contained port of the live decision path (extractor subset -> protocol
gap evaluation -> interaction screening -> cascading classifier with the
subsumption rule and the red-flag tie-break). This suite is what makes that
claim credible: it loads the artifact by file path — exactly as a reviewer
would, with no app/* package on its import path — and asserts the
(category, urgency, owner) triple matches `app.services.bottleneck.classify`
on every note in the shipped 176-note corpus.

If a rule changes in app/** and the frozen copy is not updated, this fails
naming the exact patients that diverged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.nlp.extractor import extract
from app.services.bottleneck import classify

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
ARTIFACT_PATH = REPO_ROOT / "foundry_export" / "aip_logic_classify_bottleneck.py"
NOTES_PATH = BACKEND_ROOT / "app" / "data" / "patient_notes.json"

CORPUS = json.loads(NOTES_PATH.read_text())

REQUIRED_WRITEBACK_KEYS = {
    # Bottleneck object properties (01_ontology_spec.md) ...
    "category", "urgency", "owner", "protocol_key", "evidence_span", "summary",
    # ... plus the two Workshop display properties.
    "recommended_action", "citation",
}


def _load_artifact():
    """Load the artifact by path, the way a Functions repo would consume it —
    no reliance on the backend package layout."""
    spec = importlib.util.spec_from_file_location(
        "aip_logic_classify_bottleneck", ARTIFACT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ARTIFACT = _load_artifact()


def test_corpus_is_the_full_176():
    assert len(CORPUS) == 176, "corpus size changed — parity claim must be restated"


def test_artifact_is_self_contained():
    """The artifact must not import anything from the backend app package —
    that is the whole point of carrying frozen copies."""
    source = ARTIFACT_PATH.read_text()
    for forbidden in ("from app", "import app"):
        assert forbidden not in source, (
            f"artifact imports the local backend ({forbidden!r}); "
            "it must stay self-contained"
        )


def test_writeback_dict_shape():
    """Returned dict carries exactly the Bottleneck writeback properties."""
    row = CORPUS[0]
    out = ARTIFACT.classify_bottleneck(row["note_text"], row["age"])
    assert set(out) == REQUIRED_WRITEBACK_KEYS
    assert out["category"] in {
        "missing_soc", "med_risk", "awaiting_consult", "awaiting_imaging",
        "readmit_risk", "dispo_delay", "clear",
    }
    assert out["urgency"] in {"red", "amber", "green"}


def test_evidence_span_is_verbatim_from_note():
    """Citation-backed means literally: the evidence span must be a substring
    of the source note for every non-clear classification."""
    checked = 0
    for row in CORPUS:
        out = ARTIFACT.classify_bottleneck(row["note_text"], row["age"])
        if out["category"] == "clear":
            continue
        assert out["evidence_span"], f"{row['patient_id']}: empty evidence span"
        assert out["evidence_span"] in row["note_text"], (
            f"{row['patient_id']}: evidence span not found verbatim in note"
        )
        checked += 1
    assert checked > 0


@pytest.mark.parametrize("row", CORPUS, ids=lambda r: r["patient_id"])
def test_parity_with_live_classifier(row):
    """(category, urgency, owner) must match the live backend on every note."""
    note = row["note_text"]

    live = classify(note, extract(note)).primary
    live_triple = (live.category, live.urgency, live.owner)

    ported = ARTIFACT.classify_bottleneck(note, row["age"])
    ported_triple = (ported["category"], ported["urgency"], ported["owner"])

    assert ported_triple == live_triple, (
        f"{row['patient_id']} ({row.get('template_name', '?')}): "
        f"artifact {ported_triple} != live {live_triple}"
    )


def test_parity_is_deterministic():
    """Same note in, same answer out — twice, on a handful of notes."""
    for row in CORPUS[::40]:
        first = ARTIFACT.classify_bottleneck(row["note_text"], row["age"])
        second = ARTIFACT.classify_bottleneck(row["note_text"], row["age"])
        assert first == second
