# Changelog

Reverse-chronological log of the major waves of work on **Bottleneck
Radar**, a Palantir Build Challenge entry. Each entry is grounded in the
real git history (`git log --oneline`) and the numbers are reproduced by
the commands listed at the bottom — not asserted.

The product is an operational coordination tool for hospital throughput.
It is **not a clinical decision aid**; there is no LLM in the
recommendation path.

---

## Weekend wave — trajectory, floor memory, provability, demo polish

Commits: `18c3d06` (longitudinal trend engine), `8cd280d` (trajectory UI,
census/handoff snapshots, rigor layer, demo polish), `5140314` (review
fixes: resolved-gap honesty, StoryMode key isolation). Dated 2026-06-13.

- **Longitudinal trajectory.** A trend engine (`app/services/trends.py`)
  reads a patient's prior notes plus the current note and composes a
  trajectory narrative: per-lab direction with a clinical verdict (lactate
  *clearing* vs. creatinine *worsening*), recurrent-admission cues, and a
  **"gaps closed across notes"** block — protocol steps that were missing
  earlier and are documented now. This distinguishes *never-done* (a real
  bottleneck) from *done-and-resolved* (no action needed).
- **Narrative-only by construction.** The classifier never sees prior
  notes; it reads only the current `note_text`. History changes the story
  the console tells, not the decision the rules make — so category
  accuracy stays **100% (176/176)** by construction, not by tuning. The
  resolved-gap rule was hardened in `5140314` to require the protocol to
  still trigger and the specific action to have moved out of its missing
  set, so a protocol that merely stops firing is never mislabeled
  "resolved."
- **Floor memory.** Census snapshots (`CensusSnapshot`,
  `GET /census/series`) give `/analytics` a real census/acuity trend line
  instead of one instantaneous number; the LIVE TICK captures one each
  tick. Handoffs can be finalized into immutable artifacts
  (`HandoffSnapshot`, `POST /census/handoff/finalize`,
  `GET /census/handoff/{id}`).
- **Provability layer.** A read-only provenance export
  (`app/services/audit.py`, `GET /audit/patient/{id}`,
  `GET /audit/corpus/summary`) re-verifies every evidence span against its
  note (`note_text[start:end] == span.text`). On the live corpus,
  **404 / 404 spans verify (100%, zero offenders)**; citation coverage is
  **67.09%** corpus-wide (212 / 316 signals) — 100% of guideline-derived
  signals are cited, and operational categories carry no citation by
  design. Backed by property tests (determinism + span integrity),
  adversarial fuzz tests, and an audit-invariant test, all documented in
  `backend/docs/MODEL_CARD.md`.
- **StoryMode.** A guided, keyboard-driven demo tour (`★ STORY` in the
  titlebar, the command palette, or `Shift+S`) that walks the whole
  product as one narrated story; `5140314` isolated its key handling so
  the tour can't be yanked off-route by other global shortcuts.
- **Suite grew to 382 tests** (adds trends, census, audit, property, and
  fuzz coverage), green in under twenty seconds.

---

## Tuning-to-100% wave — SLA loop, capacity, sandbox, eval, interactions

Commit: `9d1dbb8` ("Expand Bottleneck Radar: SLA/capacity/sandbox/eval/
interactions + tuning to 100%"). Dated 2026-06-13.

- **Closing the loop.** Every coordination action gets an SLA deadline
  from an ops-owned policy table (`app/services/sla.py`), moves through an
  explicit state machine, and writes an `ActionEvent` audit row on every
  transition; a breach sweep (`POST /actions/sweep`) escalates anything
  past deadline.
- **Capacity / What-If.** A deterministic residual-LOS model
  (`GET /capacity/forecast`, `POST /capacity/simulate`) projects the 48h
  census and answers "if we cleared this blocker class, how many beds and
  when." On the demo corpus, resolving every `dispo_delay` frees
  **+32 beds within 24h**; every number traces to a stated assumption.
- **Triage sandbox.** Paste any note and watch the 4-stage pipeline run
  with evidence highlighting and per-stage millisecond timings — the
  "no LLM in the recommendation path" claim made checkable on screen.
- **Eval, made honest.** Scored continuously in the API
  (`GET /eval/summary`, `GET /eval/misses`), on the `/analytics` model
  card, and in `tools/eval_harness.py`: **category 100% (176/176)**,
  **owner routing 90.91% (160/176)**. The headline honesty caveats: the
  corpus is 4 generated notes per template, so 100% means all 44
  bottleneck templates are handled — **not** robustness to arbitrary
  paraphrase; and the 16 owner misses are a documented labeling
  inconsistency (the corpus labels `awaiting_imaging` as `physician`, the
  canonical routing table uses `nurse`), deliberately taken rather than
  special-cased away.
- **Medication safety as data.** A declarative, citation-backed
  drug-interaction engine (`app/services/interactions.py`) with 13 rules,
  negation-aware and brand-name-normalizing.

---

## Expansion wave — protocols, corpus, console screens, tests

Commits: `633d934` (12 pathways, 176-note corpus), `bd08c4c` (floor map,
analytics, handoff, audit-trail, bulk-action endpoints), `d38000a`
(pytest suite), `d64089f` (floor/analytics/handoff pages, command palette,
shortcuts), `762dad0` (styling, command palette, audit block, print
mode), `afee53d` (README rewrite + Foundry export CSV regeneration).
Dated 2026-05-19.

- **Protocol library to 12 pathways**, each encoded as data (triggers,
  expected actions, owner, urgency, time window, citation), with the
  corpus expanded to **176 notes** carrying held-out truth labels.
- **Seven console screens** beyond the queue and patient detail: floor
  map (180 beds across 6 wings), analytics, printable shift handoff, plus
  the bulk-action and audit-trail endpoints behind them.
- **First pytest suite** covering extractor, protocols, classifier, ICD,
  and the API.
- **UI build-out:** command palette (`⌘K`), keyboard shortcuts, bulk
  select, print mode, and the editorial landing page.
- **Foundry export refreshed:** README rewrite and regenerated export
  CSVs so the local backend and the Foundry port stay in parity.

---

## Initial build

Commit: `9ed1d38` ("palantir first commit ofc"). Dated 2026-04-27.

- The first cut of the deterministic pipeline: rules/regex entity
  extraction with NegEx-lite negation, a citation-backed protocol matcher,
  the bottleneck cascade classifier, and the FastAPI + SQLite backend with
  the React/TypeScript console — the foundation everything above builds on.

---

## Reproducing the headline numbers

```bash
cd backend

# Test count (382).
.venv/bin/python -m pytest tests/ -q

# Category + owner accuracy (100% / 90.91%).
.venv/bin/python tools/eval_harness.py

# Provability: pct_verified (100.0) and pct_cited (67.09).
.venv/bin/python -c "from app.db.database import SessionLocal; \
from app.services import audit; db=SessionLocal(); \
s=audit.build_corpus_summary(db); \
print({k:v for k,v in s.items() if k!='unverified_spans'}, 'offenders=', len(s['unverified_spans'])); db.close()"
```

Or live, with the dev server up: `curl -s localhost:8001/audit/corpus/summary`.
