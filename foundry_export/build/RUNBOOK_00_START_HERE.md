# RUNBOOK 00 — START HERE

**Goal for today:** go from *just logged in* to *recording-ready in Foundry* for the **THIN SLICE** — the minimum build that makes "functional workflow built in Foundry + AIP" literally true on camera.

**Thin slice = six object types.** 4 datasets → 6 ontology objects (Patient, Note, Protocol, ProtocolStep, Bottleneck, Action) → 1 Pipeline (protocol-gap) → 1 Function (classify_bottleneck) → 2-screen Workshop app. (If short on time, Protocol/ProtocolStep and Action can be cut — the absolute minimum is Patient + Note + Bottleneck + the Function + a 2-screen app.) Everything else (NoteVersion trajectory, InteractionFlag, eval_labels, snapshots, automations, Pipeline 1 LLM enrichment) is **optional / post-record**.

**Total critical-path time: ~3h 30m – 4h 30m.** Budget a full morning. Do the token step first thing — nothing else works until it's done.

> Open the sub-runbooks as you reach each step. They live in this folder (`foundry_export/build/`): `RUNBOOK_ontology.md`, `RUNBOOK_pipelines.md`, `../function_repo/README.md`, `RUNBOOK_workshop.md`.

---

## CRITICAL PATH vs OPTIONAL — read this first

**CRITICAL PATH (do these, in order — this is the whole recording):**

1. Mint token + configure pltr-cli + verify
2. Upload the 4 datasets (`python upload_csvs.py`)
3. Apply/infer schema on the 4 datasets
4. Build the core-five ontology (Patient, Note, Protocol, ProtocolStep, Bottleneck, Action)
5. Build Pipeline 2 (protocol-gap transform) → `protocol_gaps` dataset
6. Author + deploy the `classify_bottleneck` Function → writes `Bottleneck`
7. Build the 2-screen Workshop app
8. Pre-record sanity check
9. Record

**OPTIONAL (skip for the thin slice — say "build after the core five" if asked on camera):**

- `eval_labels` + `note_versions` datasets (placeholder RIDs in `upload_csvs.py` — **not needed**, leave them)
- NoteVersion object + trajectory Function (narrative-only history)
- InteractionFlag object + interaction engine
- Pipeline 1 (LLM note-enrichment / ICD-10 rail) — the ICD-10 right-rail is cosmetic; the recommendation path does not use it
- CensusSnapshot / HandoffSnapshot / ActionEvent + the scheduled Automations
- SLA escalation sweep

If you run short on time, cut from the bottom of the optional list up. The critical path alone satisfies the challenge brief.

---

## VERIFIED CORPUS NUMBERS (computed locally over all 176 notes — use for narration + sanity checks)

These are the exact figures the deterministic engine produces on the demo corpus.
They match the local app's live screens 1:1. Quote these on camera with confidence.

| Figure | Value | Where it shows |
|---|---|---|
| Patients (census) | **176** | Queue KPI "In census" |
| Critical (urgency red) | **44** | Queue KPI "Critical" |
| Elevated (amber) | **84** | Queue KPI "Elevated" |
| Routine (green) | **48** | Queue KPI "Routine" |
| `protocol_gaps` rows (Pipeline 2 output) | **136** | STEP 5 sanity check — dataset row count |
| Patients with ≥1 protocol gap | **56** | narration: "56 with documentation gaps" |
| `missing_soc` bottlenecks ("silent failures") | **52** | Queue KPI "Silent failures" proxy |
| Owner split | physician 80 · case_manager 44 · pharmacist 20 · nurse 16 · *(clear: 16 blank)* | Queue table owner column |

> **Heads-up, not a bug:** 16 patients are `clear` (no bottleneck) and therefore have a
> blank `owner`/`category`/`recommended_action`. A blank row in the owner column is
> correct for those — don't mistake it for a broken binding on camera.

---

## THE ORDERED CHECKLIST

### STEP 1 — Mint a fresh Foundry token + wire up pltr-cli  ⏱ ~10 min  · CRITICAL · BLOCKS EVERYTHING
> Your token **expired ~45 days ago.** Nothing below works until this is green.

- [ ] In the Foundry UI (`https://srujan.usw-17.palantirfoundry.com`), open **Account → Settings → Tokens** (or **User Settings → API tokens**) and **generate a new token**. Copy it now — you cannot see it again.
- [ ] Configure the CLI (pltr-cli 0.15.0 is at `~/.local/bin/pltr`):
      ```
      ~/.local/bin/pltr configure configure --profile default
      ```
      When prompted: host = `https://srujan.usw-17.palantirfoundry.com`, token = the one you just minted. This writes to macOS keyring **service `pltr-cli`, account `default`** — the exact slot `upload_csvs.py` reads.
- [ ] Verify connectivity:
      ```
      ~/.local/bin/pltr verify
      ```
      Must return a healthy / authenticated result. If it 401s, the token didn't save — re-run `configure`. **Do not proceed until this passes.**

### STEP 2 — Upload the 4 thin-slice datasets  ⏱ ~5 min  · CRITICAL
> `upload_csvs.py` reads the token from keyring (`pltr-cli` / `default`) and pushes a fresh SNAPSHOT to each of the 4 pre-existing dataset RIDs already hard-coded in the script.

- [ ] Run from `foundry_export/` **in the backend venv** (it has `keyring` + `requests`):
      ```
      cd /Users/srujanyamali/Downloads/Coding/Websites/Palantir/foundry_export
      source ../backend/.venv/bin/activate   # the venv with keyring + requests (verified present)
      python upload_csvs.py
      ```
- [ ] Confirm 4 datasets commit: **patients, notes, protocols, icd10_reference** each print `✓ committed`.
- [ ] **Expected & fine:** `eval_labels` and `note_versions` print `placeholder RID — skipping`. Those are optional and not in the thin slice. Leave them.

### STEP 3 — Apply / infer schema on each dataset  ⏱ ~10 min  · CRITICAL
> `upload_csvs.py` only writes files + commits. CSV columns are untyped until you apply a schema.
> **(STEP 1 + 2 are DONE — token authed, all 4 files uploaded & read-back-verified on master 2026-06-24.)**

- [ ] For each of the 4 datasets, open its dataset page in Foundry → **Apply schema** (infer from CSV). Confirm column types: `age`→Integer, `arrival_time`→Timestamp, rest String.
- [ ] **`notes` dataset — DO NOT SKIP THIS (verified live):** `note_text` is valid RFC-4180 with quoted multiline cells — **all 176 notes contain embedded newlines.** In the schema/parse dialog, enable **multiline** parsing with **quote char `"`**. Then confirm the dataset shows **exactly 176 rows**. If it shows ~904 rows, multiline parsing is OFF — fix it before continuing, or every note will be shredded across rows and the whole demo breaks.
- [ ] `patients` should show **176 rows**; `protocols` **47 rows**; `icd10_reference` **39 rows**.
- [ ] Alternatively, let **Pipeline Builder / Code Repositories prompt you** to infer the schema on first use (Step 5) — but doing it now avoids a mid-pipeline surprise.

### STEP 4 — Build the core-five ontology  ⏱ ~45–60 min  · CRITICAL
> Full instructions: **`RUNBOOK_ontology.md`**. Names must match the CSVs 1:1 or the transform won't map.

- [ ] Create Foundry **Project** `bottleneck-radar` (if it doesn't exist).
- [ ] Object types from `01_ontology_spec.md`: **Patient**, **Note**, **Protocol**, **ProtocolStep**, **Bottleneck**, **Action**.
- [ ] Links: `Note → Patient`; `ProtocolStep → Protocol`; `Bottleneck → Patient`; `Action → Patient`.
- [ ] Paste the disclosure strings into `Patient.description` and `Bottleneck.description` (verbatim from the spec — protects the use-case-restriction posture on camera).
- [ ] **SKIP** (optional): NoteVersion, InteractionFlag, Icd10Code-as-object (keep ICD-10 as a raw dataset), EvalLabel (dataset only), snapshot/audit objects.

### STEP 5 — Build Pipeline 2: protocol-gap detection  ⏱ ~30–45 min  · CRITICAL
> Full instructions: **`RUNBOOK_pipelines.md`**. Spec: `02_pipeline_and_function_spec.md`.

- [ ] Build this in a **Python Transforms repository (Code Repositories)** — NOT Pipeline Builder. The transform file is a self-contained module with its own `def transform(notes)` + `SparkSession`; Pipeline Builder's Python node cannot accept it. See `RUNBOOK_pipelines.md` → "which product" callout.
- [ ] Source = `notes` ONLY (columns `patient_id`, `note_text`). Do NOT wire `protocols` — the rules are inlined in the transform; `protocols` is kept in source control for traceability only.
- [ ] Paste `pipeline_protocol_gap_transform.py` **verbatim** (it's generated — never hand-edit) and wrap it with the repo's `@transform` Input/Output binding.
- [ ] Output dataset = `protocol_gaps` with the schema from `OUTPUT_SCHEMA` in the transform.
- [ ] Run it; confirm the `protocol_gaps` dataset has **136 rows** across **56 patients** (verified count). P-1001 has a sepsis row whose missing step is "Administer broad-spectrum antibiotics".
- [ ] **SKIP** (optional): Pipeline 1 (LLM enrichment + ICD-10 ranking). Not on the recommendation path.

### STEP 6 — Author + deploy the classify_bottleneck Function  ⏱ ~30–45 min  · CRITICAL
> Full instructions: **`../function_repo/README.md`**. Source: `aip_logic_classify_bottleneck.py` (self-contained, stdlib-only).

- [ ] Register as a **Functions (Python)** function from `aip_logic_classify_bottleneck.py`. Entry point: `classify_bottleneck(note_text, age)`.
- [ ] **Inputs:** bind `note_text` ← `Note.note_text`, `age` ← `Patient.age` (age is unused by the rules but part of the signature — bind it so the call type-checks).
- [ ] **Output:** the function returns exactly **8 keys** — `category, urgency, owner, protocol_key, evidence_span, summary, recommended_action, citation`. **`patient_id` is NOT returned** — the Bottleneck PK comes from the writeback binding (the Patient it ran against), not a return field. See `RUNBOOK_ontology.md` §3.
- [ ] Run/backfill per Patient so every Patient gets one Bottleneck. Spot-check **P-1001** = `missing_soc` / red / physician, `protocol_key=sepsis`.
- [ ] Expose via Function binding so Workshop can re-run ("Why stuck?").

### STEP 7 — Build the 2-screen Workshop app  ⏱ ~45–60 min  · CRITICAL
> Full instructions: **`RUNBOOK_workshop.md`**. Storyboard: `03_workshop_storyboard.md`.

- [ ] **Screen 1 — Queue** (`/dashboard`): header strip + disclaimer badge, KPI metric cards (census / critical / elevated / routine / silent-failures / open-actions), filter bar, **Object Table** of Patient ⋈ Bottleneck. Row click → Screen 2.
- [ ] **Screen 2 — Patient detail** (`/p/{patient_id}`): bottleneck card with "Why this fired", note text, care-pathway gap table, **+ Create action from recommendation** button (Action Type `create-coordination-action`).
- [ ] Wire the **create-coordination-action** Action Type (writes Action with `status=open`, `title = bottleneck.recommended_action`, `owner_role = bottleneck.owner`).
- [ ] **SKIP** (optional): trajectory panel, ICD-10 rail, entity chips, Start/Resolve/Escalate buttons, snapshots. The Create-action click is the one mutation you must demo.

### STEP 8 — PRE-RECORD SANITY CHECK  ⏱ ~15 min  · CRITICAL
> See the dedicated section below. Do every line before you hit record.

### STEP 9 — Record  ⏱ ~30 min (incl. retakes)
- [ ] Follow `06_demo_video_script.md` (90-second narration path). Keep runtime < 4:00.
- [ ] Optional local reference app for B-roll: `./run-demo.sh` from repo root.

---

## PRE-RECORD SANITY CHECK — confirm each layer works before hitting record

Click through this top-to-bottom. If any line fails, fix that layer before recording — the whole point is that the build is real on camera.

**Auth layer**
- [ ] `~/.local/bin/pltr verify` still returns authenticated (token not re-expired mid-session).

**Data layer**
- [ ] Open each of the 4 datasets in Foundry; each shows committed rows + an applied schema (typed columns, not all strings). Patients ≈ 176 rows.

**Ontology layer**
- [ ] In Ontology Manager, open **Patient** → object explorer shows P-1001 with age/sex/chief_complaint.
- [ ] Open one **Patient** instance and confirm its linked **Note** resolves (link is live, not empty).

**Pipeline layer**
- [ ] Open the `protocol_gaps` dataset → it has rows, and P-1001 has a sepsis row with a missing antibiotics step (the headline demo beat).

**Function layer**
- [ ] Open the **Bottleneck** object set → P-1001's Bottleneck = category `missing_soc`, urgency `red`, owner `physician`, `recommended_action` populated. Trigger "Why stuck?" / re-run once to confirm the Function fires live.

**Workshop layer**
- [ ] Open the Workshop app **Queue** screen: KPI cards show non-zero numbers; the Patient table renders with urgency pills.
- [ ] Click P-1001 → detail screen loads, bottleneck card + "Why this fired" expand works, the note text renders.
- [ ] Click **+ Create action from recommendation** → a new Action appears with `status=open` and the recommended title. **This is the money shot — confirm it actually writes.** (After testing, you may want to delete the test Action so the open-actions KPI starts clean for the take.)

**Recording hygiene**
- [ ] Browser zoomed/sized so text is legible; close unrelated tabs; disclaimer badge ("Operational coordination tool. Not a clinical decision aid.") is visible on screen 1.

If all boxes are checked: you are recording-ready in Foundry. Go.
