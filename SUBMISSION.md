# Build Challenge submission checklist — Bottleneck Radar

Deliverable: a **< 4-minute unlisted YouTube demo video** sent to the
recruiter, showing a functional workflow built with Foundry + AIP.
This file maps every requirement in the challenge brief to where this
project satisfies it, then lists the steps only a human can finish.

---

## Requirement → where it's satisfied

| Challenge requirement | Where this project satisfies it |
| --------------------- | ------------------------------- |
| **Functional workflow in Foundry + AIP** | `foundry_export/` is the port kit: `01_ontology_spec.md` (Patient, Note, Protocol, ProtocolStep, Bottleneck, Action object types + links), `02_pipeline_and_function_spec.md` (Pipeline Builder transforms + the deterministic classifier as an AIP Logic function), `03_workshop_storyboard.md` (the console screens in Workshop), `pipeline_protocol_gap_transform.py` (self-contained transform), `build_csvs.py` / `upload_csvs.py` (dataset layer). The local FastAPI + React app is the working reference implementation of the same workflow. **Human step remaining: build the Workshop app in your Foundry instance** (below). |
| **Video: < 4 min, unlisted YouTube** | Shot-by-shot script with timing column at `foundry_export/06_demo_video_script.md` — 3:45 planned runtime against a 4:00 ceiling, plus pre-flight checklist and live-fallback notes. |
| **Show WHY this problem** | Cold open (0:00–0:20 in the script): hospitals lose beds to coordination failures, not medicine. README intro makes the same case in print. |
| **Show WHO the users are** | Charge nurse (queue), physician / nurse / pharmacist / case manager (owner routing), bed manager (capacity what-if), throughput lead (SLA policy table). Named explicitly in the script beats and the README taxonomy table. |
| **Show IMPACT** | The capacity beat (1:35–2:15): resolving every `dispo_delay` frees +32 beds within 24h on the demo corpus, with the 32 named patients whose discharge moves — verified by `POST /capacity/simulate`. SLA escalation + audit trail close the loop from signal to action. |
| **Under the hood / technical choices** | The sandbox beat (0:55–1:35): live 4-stage pipeline trace with evidence highlighting, NegEx-lite negation tags, and ms timings. README "The pipeline" + "Measured, not asserted" sections document the architecture and the eval methodology. |
| **Own every implementation decision** | Every design stance is written down and defensible: deterministic citation-backed rules with **no LLM in the recommendation path** (the AIP Use Case Restriction position for clinical settings); operational coordination tool, **not** a clinical decision aid; 100% corpus accuracy claimed only with its caveat (4 notes per template ⇒ 44/44 templates handled, **not** paraphrase robustness); the 16 owner-routing misses are a documented labeling inconsistency in the synthetic corpus, shown by name on the model card instead of being relabeled away; the capacity model returns its full assumptions table in every response; a 0.97 regression gate (`backend/tests/test_sandbox_eval.py`) guards every rule change. |
| **Terms of Service / data permissions** | All 176 patients are notional, generated from 44 templates — no PHI, no real chart text, nothing scraped. The AIP Now / developer-tier terms apply to the Foundry instance used; nothing in this project uploads restricted or third-party data. The tool is explicitly not a medical device and not a clinical decision aid (README "What it isn't"). |

Numbers in this file, reproduced by command:
`pytest tests/ -q` (backend suite passes), `tools/eval_harness.py`
(100% / 176-of-176 primary category — 44/44 templates, see caveat
above; 90.9% / 160-of-176 owner routing), and
`POST /capacity/simulate {"resolve_categories": ["dispo_delay"]}`
(+32 free beds at the 24h checkpoint, 32 patients moved).

---

## Remaining human steps (in order)

Only you can do these. Everything else is in the repo.

1. **Upload the data layer to Foundry.** From `foundry_export/`:
   `python build_csvs.py` if you need to regenerate, then
   `python upload_csvs.py` (expects your pltr-cli token in the macOS
   keyring; dataset RIDs for your instance are at the top of the script).
2. **Create the ontology** in Ontology Manager per
   `foundry_export/01_ontology_spec.md` — object types, properties, and
   links named to match the CSVs one-to-one.
3. **Stand up the pipeline** per `02_pipeline_and_function_spec.md`:
   the protocol-gap transform in Pipeline Builder
   (`pipeline_protocol_gap_transform.py` is the self-contained source)
   and the classifier as an AIP Logic function writing to `Bottleneck`.
4. **Build the Workshop app** per `03_workshop_storyboard.md` (queue
   screen + patient screen). This is what makes the "functional
   workflow in Foundry" requirement literally true on camera.
5. **Rehearse, then record** per
   `foundry_export/06_demo_video_script.md`. Do the pre-flight
   checklist completely — especially the re-ingest and the
   create-the-breaching-action step 65+ minutes before recording.
6. **Upload to YouTube as Unlisted.** Confirm the runtime is under
   4:00. Watch it once end-to-end at full volume before sending.
7. **Email the recruiter** the unlisted link. One short paragraph:
   what it is, the stack (Foundry + AIP port of a deterministic
   clinical-operations pipeline), and that all data is notional.

---

## Compliance notes (state these if asked, and in the video)

- **Data:** 100% notional. 176 synthetic patients from 44 templates,
  generated by `backend/app/data/generate_notes.py`. No PHI, no real
  notes, no scraped content. Truth labels exist only for evaluation.
- **Terms:** built and demoed under the AIP Now / developer-tier terms
  of the Foundry instance; no production, commercial, or clinical use.
- **Scope:** operational coordination tool. Not a clinical decision
  aid, not a diagnostic, not a medical device. No LLM in the
  recommendation path; every recommendation is a deterministic,
  citation-backed protocol-gap rule. All clinical judgment remains
  with the care team.
