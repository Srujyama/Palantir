"""
Regenerate pipeline_protocol_gap_transform.py from the live backend modules.

The Foundry transform must never drift from the local engine. This script
reads the CURRENT rule data and context/negation logic from:

  backend/app/protocols/library.py        (the 12-protocol library)
  backend/app/services/silent_failure.py  (negation / historical / resolution
                                           / ambiguity semantics)

and writes a self-contained pipeline_protocol_gap_transform.py:

  * rule data (PROTOCOLS, negation token lists, resolution phrases,
    ambiguity gates) is serialized from the imported modules, and
  * the context-handling functions are lifted verbatim from
    silent_failure.py via inspect.getsource, so even logic changes
    propagate without a hand-port.

Run:  python sync_transform.py

Output is byte-stable: running it twice produces identical files. The
backend test suite (backend/tests/test_foundry_parity.py) re-runs the
generator and diffs it against the checked-in transform, so forgetting to
regenerate after a rule change is a CI failure, not a silent divergence.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.protocols.library import PROTOCOLS as LIB_PROTOCOLS  # noqa: E402
from app.services import silent_failure as sf  # noqa: E402

OUT_PATH = HERE / "pipeline_protocol_gap_transform.py"


# ---------------------------------------------------------------------------
# Literal formatting — prefer raw strings for regexes (readable in review),
# verified to round-trip; fall back to repr() when raw can't represent it.
# ---------------------------------------------------------------------------

def _fmt_str(s: str) -> str:
    if '"' not in s and "\n" not in s and not s.endswith("\\"):
        lit = f'r"{s}"' if "\\" in s else f'"{s}"'
        try:
            if ast.literal_eval(lit) == s:
                return lit
        except (SyntaxError, ValueError):
            pass
    return repr(s)


def _fmt_str_list(items: List[str], indent: int) -> str:
    pad = " " * indent
    body = "".join(f"{pad}    {_fmt_str(s)},\n" for s in items)
    return "[\n" + body + pad + "]"


def _fmt_str_dict(d: Dict[str, List[str]], indent: int) -> str:
    pad = " " * indent
    body = "".join(
        f"{pad}    {_fmt_str(k)}: {_fmt_str_list(v, indent + 4)},\n"
        for k, v in d.items()
    )
    return "{\n" + body + pad + "}"


# ---------------------------------------------------------------------------
# Generated sections
# ---------------------------------------------------------------------------

def _protocols_block() -> str:
    chunks: List[str] = ["PROTOCOLS: List[Dict[str, Any]] = ["]
    for p in LIB_PROTOCOLS:
        chunks.append("    {")
        chunks.append(f'        "key": {_fmt_str(p.key)},')
        chunks.append(f'        "name": {_fmt_str(p.name)},')
        chunks.append(f'        "owner": {_fmt_str(p.owner)},')
        chunks.append(f'        "urgency": {_fmt_str(p.urgency_if_incomplete)},')
        chunks.append(f'        "time_window_hours": {p.time_window_hours},')
        chunks.append(f'        "citation": {_fmt_str(p.citation)},')
        chunks.append(f'        "triggers": {_fmt_str_list(p.triggers, 8)},')
        chunks.append('        "actions": [')
        for a in p.expected_actions:
            chunks.append("            {")
            chunks.append(f'                "key": {_fmt_str(a.key)},')
            chunks.append(f'                "severity": {_fmt_str(a.severity)},')
            chunks.append(f'                "label": {_fmt_str(a.label)},')
            chunks.append(
                f'                "documented": {_fmt_str_list(a.documented_patterns, 16)},'
            )
            chunks.append("            },")
        chunks.append("        ],")
        chunks.append("    },")
    chunks.append("]")
    return "\n".join(chunks)


def _context_rules_block() -> str:
    return "\n".join([
        "_NEGATION_TOKENS_LEFT = " + _fmt_str_list(sf._NEGATION_TOKENS_LEFT, 0),
        "_HISTORICAL_TOKENS = " + _fmt_str_list(sf._HISTORICAL_TOKENS, 0),
        f"_NEGATION_WINDOW = {sf._NEGATION_WINDOW}",
        "_SENTENCE_BOUNDARY = re.compile(" + _fmt_str(sf._SENTENCE_BOUNDARY.pattern) + ")",
        "",
        "_PROTOCOL_RESOLUTION_PHRASES: Dict[str, List[str]] = "
        + _fmt_str_dict(sf._PROTOCOL_RESOLUTION_PHRASES, 0),
        "",
        "_AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: Dict[str, List[str]] = "
        + _fmt_str_dict(sf._AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT, 0),
    ])


def _lifted_functions_block() -> str:
    """Lift the context-handling functions verbatim from silent_failure.py."""
    funcs = [
        sf._is_negated_or_historical,
        sf._ambiguous_trigger_passes,
        sf._find_first,
        sf._any_match,
        sf._protocol_resolved,
    ]
    return "\n\n".join(inspect.getsource(fn).rstrip() for fn in funcs)


# ---------------------------------------------------------------------------
# Static template sections (placeholders are substituted with .replace)
# ---------------------------------------------------------------------------

_HEADER = '''\
"""
Pipeline Builder — Python transform: protocol-gap detection.

GENERATED FROM backend/app/protocols/library.py and
backend/app/services/silent_failure.py — do not edit by hand; regenerate
with:  python sync_transform.py
Parity with the local engine is enforced by
backend/tests/test_foundry_parity.py over the full 176-note corpus.

Self-contained. Paste this whole file into a Pipeline Builder Python
transform node. The protocol library and the context/negation rules are
inlined so there are no imports beyond pyspark and the standard library.

Inputs (two Foundry datasets, joined by patient_id):
  - notes:       columns [patient_id (string), note_text (string)]
  - protocols:   not used at runtime — kept in source control for traceability
                 and for re-derivation if rules change. The rules below are
                 the source of truth for this transform.

Output dataset:
  protocol_gaps — one row per (patient, triggered protocol, missing step)

Output schema:
  patient_id              string
  protocol_key            string   sepsis | acs | stroke | cap | dka | pe |
                                   gi_bleed | aki | ciwa | neutropenic_fever |
                                   hyperkalemia | copd
  protocol_name           string
  action_key              string
  action_label            string   "Administer broad-spectrum antibiotics"
  action_severity         string   required | recommended
  urgency                 string   red | amber | green
  owner                   string   physician | pharmacist | nurse | case_manager
  citation                string   "Surviving Sepsis Campaign Hour-1 Bundle (2018)"
  trigger_pattern         string   the regex that triggered the protocol
  trigger_evidence        string   the literal substring of the note
  trigger_start           integer  char offset in note_text
  trigger_end             integer  char offset in note_text

If a protocol triggers but every expected step is documented, no rows are
emitted for that (patient, protocol).  If a protocol does not trigger, no
rows.  If the protocol is triggered but a resolution phrase is present, no
rows.

Context semantics (lifted verbatim from silent_failure.py):
  * negation cues ("denies", "no ", "ruled out"...) suppress a trigger only
    from the LEFT, clipped to the trigger's own sentence;
  * historical/resolution cues ("history of", "days ago", "resolved"...)
    suppress from either side, same-sentence only;
  * ambiguous triggers (e.g. "CVA", mild-AKI language) require corroborating
    context elsewhere in the note before firing;
  * per-protocol resolution phrases ("anion gap closed", "two negative
    troponins"...) retire the whole bundle for that note.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

# Pipeline Builder injects pyspark — import lazily so this file is also
# runnable as a unit test outside Foundry.
try:
    from pyspark.sql import DataFrame, SparkSession
    from pyspark.sql.types import (
        IntegerType, StringType, StructField, StructType,
    )
except Exception:  # pragma: no cover — only happens when running locally
    DataFrame = SparkSession = None  # type: ignore


# ---------------------------------------------------------------------------
# Protocol library — generated from backend/app/protocols/library.py.
# The list IS the rule engine.
# ---------------------------------------------------------------------------

'''

_CONTEXT_HEADER = '''

# ---------------------------------------------------------------------------
# Context / negation rules — generated from backend/app/services/silent_failure.py
# ---------------------------------------------------------------------------

'''

_LOGIC_HEADER = '''

# ---------------------------------------------------------------------------
# Pure-Python core (no Spark dependency) — the functions below are lifted
# verbatim from silent_failure.py by sync_transform.py.
# ---------------------------------------------------------------------------

@dataclass
class Span:
    start: int
    end: int
    text: str


'''

_DETECT_AND_TRANSFORM = '''

def detect_gaps_for_note(patient_id: str, note: str) -> List[Dict[str, Any]]:
    """Return one dict per (triggered protocol, missing step) for this note.

    Mirrors silent_failure.evaluate(): iterating patterns one at a time
    through _find_first gives the identical first surviving trigger while
    retaining which pattern produced it (for the trigger_pattern column).
    """
    rows: List[Dict[str, Any]] = []
    if not note:
        return rows

    for proto in PROTOCOLS:
        trig: Optional[Span] = None
        trig_pattern: Optional[str] = None
        for pat in proto["triggers"]:
            span = _find_first(note, [pat])
            if span is not None:
                trig, trig_pattern = span, pat
                break
        if trig is None or _protocol_resolved(note, proto["key"]):
            continue

        for action in proto["actions"]:
            if _any_match(note, action["documented"]):
                continue  # documented — not a gap
            rows.append({
                "patient_id":       patient_id,
                "protocol_key":     proto["key"],
                "protocol_name":    proto["name"],
                "action_key":       action["key"],
                "action_label":     action["label"],
                "action_severity":  action["severity"],
                "urgency":          proto["urgency"],
                "owner":            proto["owner"],
                "citation":         proto["citation"],
                "trigger_pattern":  trig_pattern,
                "trigger_evidence": trig.text,
                "trigger_start":    trig.start,
                "trigger_end":      trig.end,
            })
    return rows


# ---------------------------------------------------------------------------
# Pipeline Builder entry point
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = StructType([
    StructField("patient_id",       StringType(),  False),
    StructField("protocol_key",     StringType(),  False),
    StructField("protocol_name",    StringType(),  False),
    StructField("action_key",       StringType(),  False),
    StructField("action_label",     StringType(),  False),
    StructField("action_severity",  StringType(),  False),
    StructField("urgency",          StringType(),  False),
    StructField("owner",            StringType(),  False),
    StructField("citation",         StringType(),  False),
    StructField("trigger_pattern",  StringType(),  False),
    StructField("trigger_evidence", StringType(),  False),
    StructField("trigger_start",    IntegerType(), False),
    StructField("trigger_end",      IntegerType(), False),
]) if DataFrame is not None else None


def transform(notes: "DataFrame") -> "DataFrame":
    """Pipeline Builder calls this. Input: notes(patient_id, note_text)."""
    spark = SparkSession.builder.getOrCreate()

    def _flatten(rows: Iterator[Any]) -> Iterator[Dict[str, Any]]:
        for r in rows:
            for gap in detect_gaps_for_note(r["patient_id"], r["note_text"] or ""):
                yield gap

    rdd = notes.select("patient_id", "note_text").rdd.mapPartitions(_flatten)
    return spark.createDataFrame(rdd, schema=OUTPUT_SCHEMA)


# ---------------------------------------------------------------------------
# Local smoke test — run `python pipeline_protocol_gap_transform.py` to verify
# parity with the backend before pasting into Pipeline Builder.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, pathlib
    notes_json = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "patient_notes.json"
    if not notes_json.exists():
        print("notes file not found; smoke test skipped", file=sys.stderr)
        sys.exit(0)

    corpus = json.loads(notes_json.read_text())
    total = 0
    by_proto: Dict[str, int] = {}
    by_patient: Dict[str, int] = {}
    for n in corpus:
        gaps = detect_gaps_for_note(n["patient_id"], n["note_text"])
        total += len(gaps)
        by_patient[n["patient_id"]] = len(gaps)
        for g in gaps:
            by_proto[g["protocol_key"]] = by_proto.get(g["protocol_key"], 0) + 1

    print(f"corpus: {len(corpus)} notes")
    print(f"total gaps: {total}")
    print(f"by protocol: {by_proto}")
    patients_with_gaps = sum(1 for v in by_patient.values() if v > 0)
    print(f"patients with >=1 gap: {patients_with_gaps}")
'''


def generate() -> str:
    """Return the full text of pipeline_protocol_gap_transform.py."""
    return (
        _HEADER
        + _protocols_block()
        + _CONTEXT_HEADER
        + _context_rules_block()
        + _LOGIC_HEADER
        + _lifted_functions_block()
        + _DETECT_AND_TRANSFORM
    )


def main() -> None:
    text = generate()
    changed = (not OUT_PATH.exists()) or OUT_PATH.read_text() != text
    OUT_PATH.write_text(text)
    n_protocols = len(LIB_PROTOCOLS)
    n_actions = sum(len(p.expected_actions) for p in LIB_PROTOCOLS)
    state = "rewrote" if changed else "unchanged"
    print(f"{state} {OUT_PATH.name}: {n_protocols} protocols, "
          f"{n_actions} expected actions, {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
