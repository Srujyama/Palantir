# Bottleneck Radar — submission summary

An operational coordination console for hospital throughput. It reads the
same notes a charge nurse already reads and answers, in one screen: **who is
stuck, why, which documented step is missing, and whose job it is to move
them** — then routes that coordination work and tracks it to closure.

Built for the Palantir Build Challenge. Deterministic, citation-backed,
auditable — **no LLM in the recommendation path** by design.

---

## The one-paragraph pitch

Hospitals don't lose beds to medicine; they lose them to coordination — the
consult nobody chased, the antibiotic nobody documented, the placement
nobody called. Bottleneck Radar runs a deterministic NLP pipeline over
patient notes (extract → protocol-gap evaluation → drug-interaction screen →
cascading bottleneck classifier), surfaces the blocking step for every
patient with the exact evidence span and cited guideline, and routes it to
the right role with an SLA. Every recommendation traces to a guideline
citation and a verified evidence span — and **100% of those spans
re-verify** against the note text. The same pipeline is parity-tested and
lifts into Palantir Foundry/AIP unchanged.

---

## What it does (the surfaces)

| Surface | What it answers |
|---|---|
| **Queue** (`/dashboard`) | Every patient, urgency-ranked, with the blocking bottleneck + owner. |
| **Patient** (`/p/:id`) | Bottleneck card, evidence-highlighted note, care-pathway gap table, **trajectory** (lab trends + gaps-closed-across-notes), drug interactions, SLA-tracked actions, audit trail. |
| **Sandbox** (`/sandbox`) | Paste any note → watch the real pipeline run stage by stage, timed in ms. The "no LLM in the recommendation path" proof. |
| **Capacity** (`/capacity`) | 48h bed-census forecast + what-if scenarios ("resolve placement holds → 32 patients discharge earlier"), every number traced to a stated assumption. |
| **Analytics** (`/analytics`) | Cohort metrics, a **model card** (measured accuracy with honest caveats), and a census time-series. |
| **Floor** (`/floor`) | Spatial 180-bed view, colored by acuity, live-pulses on change. |
| **Handoff** (`/handoff`) | Printable shift artifact; finalize into an immutable, retrievable snapshot. |

A **guided demo tour** (★ STORY / Shift+S) walks the whole story hands-free.

---

## Why it's credible (the rigor)

- **Deterministic, no LLM in the recommendation path.** Pure rules over 12
  published care pathways + 13 citation-backed drug-interaction rules. The
  only optional LLM sits in note enrichment and is fenced off with a
  deterministic alternative.
- **Measured, not asserted.** Classifier scores **100% category accuracy
  (176/176)** and **90.9% owner routing** against held-out labels — with the
  honest caveat that the corpus is 4 notes per template (so 100% = all 44
  patterns handled, not paraphrase robustness), and the 16 owner misses are a
  documented labeling inconsistency surfaced by name, not relabeled away. A
  CI regression gate fails any rule change that drops below 97%.
- **Auditable.** Property-based + adversarial-fuzz tests (8,000+ iterations)
  prove the classifier never crashes, is deterministic, and that **every
  evidence span verifies `note[start:end] == text`** — 404/404 corpus-wide.
- **383 automated tests.** Backend pytest suite covering every layer.
- **Foundry parity is real, not theater.** The PySpark transform and the AIP
  Logic function are codegen'd from the backend and parity-tested field-for-
  field on all 176 notes; the generator is byte-stable.

---

## Trajectory — the operational depth

The patient page distinguishes **never-done** (a real bottleneck) from
**done-and-resolved** (no action needed) by reading prior notes: it shows
labs trending ("lactate 4.1 → 3.1, clearing" vs "creatinine worsening") and
a green "gaps closed across notes" block. This is narrative only — the
classifier never sees prior notes, so the eval stays 100% by construction.

---

## Repo map

- `backend/` — FastAPI + SQLite; the pipeline, services, and 383 tests.
- `frontend/` — React + TypeScript console (8 screens, hand-rolled charts,
  no UI kit, no chart library).
- `foundry_export/` — the AIP port kit: ontology spec (01), pipeline +
  AIP Logic spec (02), Workshop storyboard (03), AIP Agent spec (04),
  Automations spec (05), demo video script (06), the codegen'd transform,
  the executable AIP Logic classifier, and 6 Pipeline-Builder-ready CSVs.
- `backend/docs/MODEL_CARD.md` — formal model card.
- `CHANGELOG.md` — build history.

## Run it

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.data.generate_notes && python -m app.ingest
uvicorn app.main:app --port 8000

# frontend (separate shell)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## Remaining human-only steps (see `SUBMISSION.md` for the full checklist)

1. Build the Workshop app in your Foundry instance per `foundry_export/03`.
2. Upload the CSVs (`foundry_export/upload_csvs.py`, after pasting your RIDs).
3. Record the <4-minute demo per `foundry_export/06_demo_video_script.md`
   (the script is dry-run-verified; the pre-flight checklist is in it).
4. Upload unlisted to YouTube; email the link to your recruiter.

All data is notional. No PHI. AIP Now developer terms apply.
