# Bottleneck Radar — Foundry Functions (Python) repo skeleton

Drop-in skeleton for publishing the `classify_bottleneck` classifier as an
**AIP Logic / Functions (Python)** function that writes back to the
`Bottleneck` object set.

The recommendation path is **deterministic and dependency-free** — `re` +
`dataclasses` only, no LLM, no ML libraries (see `requirements.txt`). Same
note in, same answer out, every time.

---

## What's in this folder

| File                              | Role                                                        |
|-----------------------------------|-------------------------------------------------------------|
| `function.py`                     | The thin `@function` wrapper. Exposes `classify_bottleneck_fn(note_text, age) -> dict`. |
| `requirements.txt`                | Empty (stdlib only). States explicitly: zero third-party deps. |
| `README.md`                       | This file.                                                  |
| `aip_logic_classify_bottleneck.py`| **You copy this in** (see Step 2). The frozen classifier.   |

---

## Step 1 — Create the Functions repository

1. In Foundry, open the **Code Repositories** application (left nav launcher).
2. **+ New repository** -> choose the **Functions** repository type ->
   language **Python**.
3. Name it e.g. `bottleneck-radar-functions`. Pick a folder under your
   project. Create.
4. Wait for the repo to initialize (it provisions the Python Functions build
   template, which provides the `@function` runtime — you do not pip-install it).

> If your org surfaces this under the **Functions** application instead of
> Code Repositories, use **Functions -> New -> Python**; the rest is identical.

---

## Step 2 — Add the files

A Foundry Python Functions repo ships with a package directory the build
discovers functions from — by default `src/<package_name>/` (the package name
is set in `setup.py` / `pyproject.toml`; the scaffold drops an
`example.py` there). **Put all three files inside that same package
directory** so the build picks up `function.py` and so the sibling-module
import below resolves:

```
<repo root>/
  setup.py  (or pyproject.toml)      <- provided by the scaffold; do not delete
  src/
    <package_name>/
      __init__.py                    <- provided by the scaffold; keep it
      function.py                    <- from this folder
      aip_logic_classify_bottleneck.py   <- COPY from foundry_export/
  requirements.txt                   <- merge/replace at repo root
```

- **`function.py`**: paste verbatim into the package dir (next to the
  scaffold's `example.py`, which you can delete).
- **`requirements.txt`**: paste verbatim; this lives at the **repo root**
  (where the scaffold's own requirements file already is), not inside the
  package dir.
- **`aip_logic_classify_bottleneck.py`**: copy the file of that name from
  `foundry_export/` (one level up from this skeleton) into the **same package
  directory as `function.py`**. Do not edit it — it is a frozen, parity-tested
  artifact. `function.py` imports it as a sibling module:

  ```python
  from aip_logic_classify_bottleneck import classify_bottleneck
  ```

  This sibling import works because both files sit in the same package. If
  Python cannot resolve it in your scaffold (some templates require absolute
  package paths), change the one import line in `function.py` to the
  package-qualified form, e.g.
  `from <package_name>.aip_logic_classify_bottleneck import classify_bottleneck`.

> Older / "flat" Functions repos (no `src/` package) instead expect the files
> at the repo root. If that's your layout, drop all three at the root; the
> sibling import is unchanged. If unsure, match wherever the scaffold's
> `example.py` already lives — put your files beside it.

> The classifier carries its own frozen copy of the protocol library,
> interaction rules, and extractor subset, so it has no imports from any
> `app/*` package — copying this one file is the whole port.

---

## Step 3 — Verify the import path, then publish

1. Open the **Functions** sidebar/tab in the repo. Foundry discovers
   `classify_bottleneck_fn` from the `@function` decorator **only if
   `function.py` is inside the package dir** (Step 2). If the function does not
   appear, the file is in the wrong place — move it next to `__init__.py`.
2. **If the build fails on `from functions.api import function`**: your
   Foundry version exposes the decorator under a different module. Change that
   **one line** in `function.py` to the form your instance uses — common
   alternatives are noted in a comment right above it
   (`from foundry_functions_api import function`,
   `from palantir_functions import function`). Nothing else changes.
3. Build the repo (the check/build button). Resolve any import error before
   publishing.
4. **Publish / tag a version.** Once green, the function is callable from
   Workshop, AIP Logic, and Actions.

---

## Step 4 — Bind to the `Patient` object type

The function takes `note_text: str` and `age: int`. Bind them so AIP Logic /
Workshop can invoke it **per patient**:

1. In the published function's bindings (or in the AIP Logic block / Workshop
   widget that calls it), set the two inputs:
   - **`note_text`** <- the linked **`Note`** object's `note_text` property.
     `Patient -> Note` is 1:1 in this corpus (link `Note.patient_id ->
     Patient.patient_id`), so resolve the Patient's linked Note and pass its
     `note_text`.
   - **`age`** <- the bound **`Patient`** object's `age` property.
2. Scope the function to the `Patient` object type so it can be run on demand
   from the patient page (the "Why stuck?" / re-run action).

> Only the **current** `Note` drives the classifier. Do **not** bind
> `note_text` from `NoteVersion` — prior notes are narrative-only and must not
> move the result.

---

## Step 5 — Wire the writeback to the `Bottleneck` object set (upsert on `patient_id`)

The returned dict's keys are exactly the `Bottleneck` writeback properties:

```
category | urgency | owner | protocol_key | evidence_span
| summary | recommended_action | citation
```

`patient_id` is **not** in the dict — supply it from the bound `Patient` and
use it as the upsert key (one active `Bottleneck` per patient).

To materialize, in the **AIP Logic** block that calls the function:

1. Call `classify_bottleneck_fn(note_text, age)` -> capture the result dict.
2. Add an **ontology edit / "Modify or create object"** step targeting the
   **`Bottleneck`** object type.
3. **Upsert key = `patient_id`** (the bound Patient's id). This guarantees one
   active Bottleneck per patient; re-running overwrites it.
4. Map the result fields onto the Bottleneck properties one-to-one:

   | Bottleneck property   | Source                                  |
   |-----------------------|-----------------------------------------|
   | `patient_id`          | bound `Patient.patient_id` (upsert key) |
   | `category`            | `result.category`                       |
   | `urgency`             | `result.urgency`                        |
   | `owner`               | `result.owner`                          |
   | `protocol_key`        | `result.protocol_key`                   |
   | `evidence_span`       | `result.evidence_span`                  |
   | `summary`             | `result.summary`                        |
   | `recommended_action`  | `result.recommended_action`             |
   | `citation`            | `result.citation`                       |

5. Publish the Logic block. Re-running the function re-materializes the
   Bottleneck for that patient (safe on a schedule — see
   `05_automations_spec.md`).

> Alternative: back the `Bottleneck` object set with a writeback dataset and
> upsert rows there on `patient_id`. The field mapping is identical.

---

## Local smoke test (optional, before publishing)

The classifier prints its writeback dict for a notional note:

```bash
python aip_logic_classify_bottleneck.py
```

Expect a JSON object with the eight keys above and no third-party imports.
