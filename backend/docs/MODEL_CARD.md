# Model Card — Clinical Bottleneck Radar (classification path)

This card documents the decision system inside Bottleneck Radar: the path that
reads a patient note and emits the bottleneck, urgency, owner, recommended
action, citation, and evidence spans. It follows the model-card format even
though, by deliberate design, there is no statistical model here — the section
on training data says "none" for a reason.

Thesis: **verifiable, not a black box.** Every claim below is checkable by a
command in this repository, not asserted on trust.

---

## 1. Intended use

- **Who:** charge nurses, hospitalists, pharmacists, and case managers
  coordinating inpatient throughput on a floor.
- **What:** surface the single operational thing blocking each patient's
  progression (a missing protocol step, a medication-safety flag, a pending
  consult/imaging, a discharge/placement delay, readmission risk), route it to
  an owner queue, and show the exact note text that justifies the flag.
- **How it is meant to be read:** as a *coordination prompt with its
  receipts*. Every recommendation links to a guideline citation (where one
  exists) and to a verified evidence span the reader can re-check against the
  chart.

### Out of scope — this is NOT a clinical decision aid

- It does **not** diagnose, dose, or recommend therapy for an individual
  patient. Recommendations are operational ("page cardiology", "pharmacy
  review", "case management owns SNF placement"), not clinical orders.
- It must not be used as the basis for a treatment decision. A licensed
  clinician owns every clinical judgment; the Radar only points at where the
  operational ball was dropped and cites the protocol that says so.
- It is trained on a **synthetic corpus** (see §6) and has not been validated
  on real PHI, against patient outcomes, or in a prospective deployment.

---

## 2. Design: deterministic, citation-backed rules

The classification path is a **cascading rule engine**, not a learned model:

1. `app/nlp/extractor.py` — rules/regex extraction of vitals, labs, meds,
   consults, imaging, dispo blockers, symptoms, risk factors, with a
   NegEx-lite negation tagger. Every finding carries the exact `Span`
   (`start`, `end`, `text`) in the source note.
2. `app/services/silent_failure.py` — matches the note against a
   citation-backed care-pathway protocol library (`app/protocols/library.py`)
   and reports required bundle steps that are **not documented** ("silent
   failures").
3. `app/services/interactions.py` — a declarative, citation-backed
   drug-interaction rule table (nephrotoxin-in-AKI, QT stacks, anticoagulant +
   bleed, triple whammy, sedation stacks, …).
4. `app/services/bottleneck.py::classify` — a fixed cascade that picks the
   most time-sensitive bottleneck (most dangerous wins), with one documented,
   clinician-reviewed tie-break (a red interaction flag carrying objective
   harm-in-progress evidence outranks an equal-urgency protocol gap).

Because the path is deterministic, the same note always yields the same
category / urgency / owner. This is enforced as a property test
(`tests/test_properties.py::test_classify_is_deterministic`), not assumed.

### No LLM in the recommendation path

There is **no language model anywhere in extraction, classification, silent-
failure detection, interaction screening, or the "why is this patient stuck"
narrative.** The narrative (`app/api/patients.py::why_stuck`) is composed
deterministically from rule rationale strings. There are no model weights, no
API calls, no nondeterminism, and nothing to "hallucinate". This is the core
of the verifiability claim: a reviewer can read the rules end to end.

---

## 3. Inputs and outputs

- **Input:** one free-text patient note (`str`). No structured EHR feed is
  required; the only field the classifier reads is `Patient.note_text`. Prior
  notes feed the trend narrative *only* and never reach `classify()`.
- **Output:** a `TriageResult` with a primary bottleneck, secondary
  bottlenecks, the list of silent failures, and per-protocol match detail.
  Each carries `category ∈ {missing_soc, med_risk, awaiting_consult,
  awaiting_imaging, dispo_delay, readmit_risk, clear}`, `urgency ∈ {red,
  amber, green}`, `owner ∈ {physician, nurse, pharmacist, case_manager,
  social_worker}` (or empty for the "clear" case), a `recommended_action`, an
  optional `citation`, and a list of evidence `Span`s.

---

## 4. Training data

**None.** This is a rule system, not a machine-learned classifier. There is no
training set, no fitted parameters, no gradient step. The "knowledge" lives in
hand-written, individually inspectable rules and in the protocol/interaction
tables, each row of which names its literature citation. There is therefore no
training-data bias to characterize in the usual sense — the relevant audit is
"are the rules and citations correct", which is a code review, not a data
audit.

---

## 5. Evaluation

### Methodology

The shipped corpus carries **176 held-out truth labels**
(`truth_bottleneck`, `expected_owner` on each `Patient` row). They never drive
runtime behavior — they exist solely to score the engine. Scoring code:
`app/services/evaluation.py`; exposed at `GET /eval/summary`.

### Results (regenerated from the live DB, n = 176)

| Metric | Result |
| --- | --- |
| Category accuracy | **100.0%** (176 / 176) |
| Owner-routing accuracy | **90.91%** (160 / 176) |

Reproduce:

```bash
cd backend
.venv/bin/python -c "from app.db.database import SessionLocal; \
from app.services.evaluation import evaluate_corpus; db=SessionLocal(); \
r=evaluate_corpus(db); print('n',r['n'],'category',r['accuracy'],'owner',r['owner_routing']); db.close()"
```

### Honesty caveats on the eval

- **4-notes-per-template caveat.** The corpus is generated from templates with
  roughly four notes per template. Held-out accuracy therefore measures
  robustness to *within-template* surface variation, **not** generalization to
  unseen clinical phrasings or unseen presentations. A 100% category number
  must be read with this in mind: it says the rules are self-consistent with
  the data that shares their assumptions, not that they would hit 100% on real
  charts.
- **`awaiting_imaging` owner labeling conflict (the honest one).** The corpus
  labels `awaiting_imaging` rows with `expected_owner = physician`, but the
  canonical routing table (`app/services/evaluation.py`, frozen by its test)
  encodes `nurse`. Both cannot be satisfied by one general rule. The engine
  keeps the canonical `nurse` routing and **deliberately takes the miss**
  rather than special-casing notes to chase the label; that conflict is a
  meaningful chunk of the 16 owner misses. This is flagged for the data owners
  rather than papered over — see the inline note in
  `app/services/bottleneck.py::_awaiting_imaging`.

---

## 6. Known limitations

- **Synthetic corpus.** All notes are synthetic. No real PHI, no outcome
  validation, no prospective use. Numbers here characterize the rule engine
  against its own synthetic distribution.
- **Paraphrase robustness untested at scale.** Adversarial fuzzing
  (`tests/test_fuzz_notes.py`) proves the pipeline never crashes and never
  emits an invalid span under mutation, but it does **not** assert that a
  paraphrase preserves the *classification*. Robustness of the answer to
  large-scale clinical paraphrase is unmeasured.
- **Regex brittleness.** Extraction is regex-based. Unusual abbreviations,
  novel drug names outside `MEDICATIONS` / `SUPPLEMENTAL_MEDICATIONS`, or
  atypical formatting can be missed. Misses are silent (a gap simply does not
  fire); they are not hallucinated. The negation handling is NegEx-lite and
  window-bounded — sophisticated nested negation can slip through.
- **Operational, not clinical.** See §1 out-of-scope. The owner routing and
  recommended actions are coordination defaults, not orders.

---

## 7. Auditability guarantee

This is the load-bearing claim and it is mechanically enforced.

**Every evidence span verifies:** for every span surfaced anywhere
(bottleneck evidence, silent-failure trigger evidence),
`note_text[start:end] == span.text`. The highlight a clinician sees *is* the
text the rule fired on, byte for byte.

**Every guideline-derived recommendation is cited:** every `missing_soc`
(protocol-bundle gap) and every `med_risk` (drug-interaction) signal carries a
literature/guideline citation — 100% of them. Purely operational categories
(`awaiting_consult`, `awaiting_imaging`, `dispo_delay`, `readmit_risk`) carry
no citation **by design**: they are logistics, not clinical recommendations,
and there is no guideline to cite for "page cardiology". `pct_cited` over the
whole corpus is therefore below 100% (operational signals are uncited on
purpose); `pct_cited` restricted to guideline-derived signals is 100%.

This is proven at runtime by the provenance export
(`app/services/audit.py`, `GET /audit/corpus/summary`).

### Corpus provenance summary (live DB)

```json
{
  "n_patients": 176,
  "n_signals": 316,
  "n_with_citation": 212,
  "pct_cited": 67.09,
  "n_evidence_spans": 404,
  "n_verified_spans": 404,
  "pct_verified": 100.0,
  "unverified_spans": []
}
```

`pct_verified == 100.0` with `unverified_spans == []`: every one of the 404
evidence spans across all 176 patients re-derives exactly from its note. The
67.09% `pct_cited` is the uncited-operational-signals effect described above
(212 of 316 signals are guideline-derived and all 212 are cited).

---

## 8. Reproduction commands

```bash
cd backend

# Full test suite (unit + property + fuzz + audit).
.venv/bin/python -m pytest tests/ -q

# Provability layer only.
.venv/bin/python -m pytest tests/test_properties.py tests/test_fuzz_notes.py tests/test_audit.py -q

# Live corpus provenance summary (pct_verified / pct_cited).
.venv/bin/python -c "from app.db.database import SessionLocal; \
from app.services import audit; db=SessionLocal(); \
s=audit.build_corpus_summary(db); \
print({k:v for k,v in s.items() if k!='unverified_spans'}, 'offenders=', len(s['unverified_spans'])); db.close()"

# Classifier scorecard (category / owner accuracy).
.venv/bin/python -c "from app.db.database import SessionLocal; \
from app.services.evaluation import evaluate_corpus; db=SessionLocal(); \
r=evaluate_corpus(db); print('n',r['n'],'category',r['accuracy'],'owner',r['owner_routing']); db.close()"
```

The provenance and scorecard endpoints are also live: `GET /audit/patient/{id}`,
`GET /audit/corpus/summary`, `GET /eval/summary`.

---

*Generated 2026-06-13. Numbers in §5 and §7 were regenerated from the live DB
at that time; re-run the commands in §8 to refresh.*
