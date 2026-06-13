"""Foundry port-kit parity tests.

The Foundry Pipeline Builder transform (foundry_export/
pipeline_protocol_gap_transform.py) is GENERATED from the live backend rule
modules by foundry_export/sync_transform.py. These tests make any drift
between the two engines a CI failure:

  1. The generator's output must match the checked-in transform byte for
     byte (i.e. someone changed library.py / silent_failure.py and forgot
     to run `python sync_transform.py`).
  2. For every note in the 176-note corpus, the transform's
     detect_gaps_for_note() must agree field-for-field with the backend's
     silent_failures(): protocol_key, protocol_name, action label,
     severity, owner, urgency, citation, and the exact trigger span
     (start / end / text).
  3. The transform's action_key values must match the protocol library's
     (protocol_key, action_label) -> action_key mapping, since the backend
     SilentFailure dataclass carries the label but not the key.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.protocols.library import PROTOCOLS
from app.services.silent_failure import silent_failures

BACKEND = Path(__file__).resolve().parents[1]
FOUNDRY = BACKEND.parent / "foundry_export"
TRANSFORM_PATH = FOUNDRY / "pipeline_protocol_gap_transform.py"
SYNC_PATH = FOUNDRY / "sync_transform.py"
NOTES_PATH = BACKEND / "app" / "data" / "patient_notes.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so the @dataclass decorator can resolve the
    # module's globals (the documented importlib recipe).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def transform():
    return _load_module(TRANSFORM_PATH, "foundry_transform")


@pytest.fixture(scope="module")
def corpus():
    return json.loads(NOTES_PATH.read_text())


def test_generated_transform_is_in_sync_with_backend_rules():
    """Regenerating from the live modules must reproduce the checked-in file.

    Fails when backend/app/protocols/library.py or
    backend/app/services/silent_failure.py changed and the port kit was not
    regenerated (fix: cd foundry_export && python sync_transform.py).
    """
    sync = _load_module(SYNC_PATH, "foundry_sync_transform")
    assert sync.generate() == TRANSFORM_PATH.read_text(), (
        "foundry_export/pipeline_protocol_gap_transform.py is stale — "
        "regenerate it with: python foundry_export/sync_transform.py"
    )


def test_transform_freezes_all_protocols(transform):
    lib_keys = [p.key for p in PROTOCOLS]
    frozen_keys = [p["key"] for p in transform.PROTOCOLS]
    assert frozen_keys == lib_keys
    lib_actions = {
        (p.key, a.key): (a.label, a.severity)
        for p in PROTOCOLS
        for a in p.expected_actions
    }
    frozen_actions = {
        (p["key"], a["key"]): (a["label"], a["severity"])
        for p in transform.PROTOCOLS
        for a in p["actions"]
    }
    assert frozen_actions == lib_actions


def _backend_rows(note: str):
    return [
        {
            "protocol_key": sf.protocol_key,
            "protocol_name": sf.protocol_name,
            "action_label": sf.missing_action,
            "action_severity": sf.severity,
            "owner": sf.owner,
            "urgency": sf.urgency,
            "citation": sf.citation,
            "trigger_start": sf.trigger_evidence.start,
            "trigger_end": sf.trigger_evidence.end,
            "trigger_evidence": sf.trigger_evidence.text,
        }
        for sf in silent_failures(note)
    ]


def _transform_rows(gaps):
    return [
        {
            "protocol_key": g["protocol_key"],
            "protocol_name": g["protocol_name"],
            "action_label": g["action_label"],
            "action_severity": g["action_severity"],
            "owner": g["owner"],
            "urgency": g["urgency"],
            "citation": g["citation"],
            "trigger_start": g["trigger_start"],
            "trigger_end": g["trigger_end"],
            "trigger_evidence": g["trigger_evidence"],
        }
        for g in gaps
    ]


def test_full_corpus_gap_parity(transform, corpus):
    """Every note: transform output == backend silent_failures, in order."""
    assert len(corpus) == 176  # guard against a truncated corpus file
    for n in corpus:
        note = n["note_text"]
        gaps = transform.detect_gaps_for_note(n["patient_id"], note)
        assert _transform_rows(gaps) == _backend_rows(note), (
            f"Foundry transform disagrees with backend engine on "
            f"{n['patient_id']} ({n.get('template_name', '?')})"
        )


def test_action_keys_match_library(transform, corpus):
    """action_key is transform-only (SilentFailure has no key field) —
    verify it against the library's (protocol_key, label) mapping."""
    key_by_label = {
        (p.key, a.label): a.key for p in PROTOCOLS for a in p.expected_actions
    }
    for n in corpus:
        for g in transform.detect_gaps_for_note(n["patient_id"], n["note_text"]):
            assert g["action_key"] == key_by_label[(g["protocol_key"], g["action_label"])]


def test_patient_id_passthrough(transform, corpus):
    for n in corpus[:10]:
        for g in transform.detect_gaps_for_note(n["patient_id"], n["note_text"]):
            assert g["patient_id"] == n["patient_id"]


def test_empty_note_yields_no_rows(transform):
    assert transform.detect_gaps_for_note("P-0000", "") == []
    assert transform.detect_gaps_for_note("P-0000", None) == []
