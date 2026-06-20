"""Foundry Functions (Python) entry point for the Bottleneck Radar classifier.

This is the thin published wrapper. All decision logic lives in the
self-contained, stdlib-only artifact ``aip_logic_classify_bottleneck.py``
(copied from ``foundry_export/`` into this repo — see README.md). This module
adds nothing but the ``@function`` decorator and a typed entry point so AIP
Logic / Workshop can invoke it per patient.

Output dict maps 1:1 onto the ``Bottleneck`` object type (01_ontology_spec.md):

    category | urgency | owner | protocol_key | evidence_span
    | summary | recommended_action | citation

The primary key ``patient_id`` is NOT computed here — it is supplied by the
bound ``Patient`` at the Logic layer and used as the upsert key when this
result is written back to the ``Bottleneck`` object set.

No LLM, no randomness, no clock: same note in, same answer out.
"""

from __future__ import annotations

# --- Decorator import -------------------------------------------------------
# Foundry's Python Functions runtime exposes the decorator here in current
# stacks. If YOUR Foundry instance resolves it elsewhere, this is the ONLY
# line to change; nothing below depends on the import path.
#
#   Common alternative forms seen across Foundry versions:
#     from functions.api import function          # (used below — most current)
#     from foundry_functions_api import function
#     from palantir_functions import function
#
from functions.api import function

# Import the frozen classifier that lives alongside this module in the repo.
# Copy aip_logic_classify_bottleneck.py into the SAME directory as this file
# (inside the scaffold's package dir, e.g. src/<package_name>/ — see README
# Step 2). This sibling import resolves because both files share a package.
# If your scaffold requires absolute package paths, change this one line to:
#   from <package_name>.aip_logic_classify_bottleneck import classify_bottleneck
from aip_logic_classify_bottleneck import classify_bottleneck


@function
def classify_bottleneck_fn(note_text: str, age: int) -> dict:
    """Classify one patient's current note into its primary operational bottleneck.

    Bindings (set these in the Functions UI when you publish):
        note_text : the linked ``Note`` object's ``note_text`` property
                    (Patient -> Note is 1:1 in this corpus).
        age       : the bound ``Patient`` object's ``age`` property. Accepted
                    to match the Patient binding; the current rule cascade
                    does not branch on it (reserved for age-gated routing).

    Returns:
        A dict whose keys are exactly the writeback properties of the
        ``Bottleneck`` object type. Materialize it as one active Bottleneck
        per patient via an ontology edit in the Logic block, upserting on the
        bound ``patient_id``.
    """
    return classify_bottleneck(note_text, age)
