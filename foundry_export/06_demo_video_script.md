# Demo video script — Bottleneck Radar

Target runtime: **3:45** (hard ceiling 4:00 per the challenge brief).
Audience: Palantir Forward Deployed Engineers and Deployment Strategists.
Tone: first person, confident, concrete. No filler, no "um, so basically."
Every number spoken below was verified against the running system —
if the screen says something different on recording day, **read the screen**.

---

## The arc

why this problem → who the users are → why these are receipts → the patient moves over time → under the hood → it's measured → the loop closes → it lifts into Foundry

The whole tour can be driven hands-free by **StoryMode** (`★ STORY` in the
titlebar, or `Shift+S`): it walks queue → critical → P-1002 → trajectory →
sandbox → capacity → model card → analytics → floor with a caption per beat,
so you can narrate over it. The manual shot list below is a superset — it
adds two beats StoryMode doesn't auto-drive (the **P-1041 medication
interactions** beat after the trajectory, and the **SLA sweep + live tick**
loop-close beat before the Foundry close). If you drive with StoryMode,
click into P-1041 and the sweep terminal manually at those two points, then
resume the tour.

---

## Shot list

| Time | On screen | Spoken line |
|------|-----------|-------------|
| 0:00–0:18 | `/dashboard` (Queue). Full table visible: KPI strip on top, urgency-ranked patient rows, OWNER column in frame. Cursor still. | "Hospitals don't lose beds to medicine — they lose them to coordination: the consult nobody chased, the antibiotic nobody documented, the placement nobody called. This is Bottleneck Radar. A hundred seventy-six patients, one screen, and the charge nurse's first question answered: who is stuck, why, and whose job is it to move them." |
| 0:18–0:38 | Click into `/p/P-1002` (Fever, hypotension, AMS). Show in order: the red **Bottlenecks** card, the **Care-pathway evaluation** table (missing step row), then hover the highlighted span in **Patient note (evidence highlighted)**. | "Here's why. This patient triggered the Surviving Sepsis hour-one bundle, and the pathway table shows broad-spectrum antibiotics aren't documented. That claim isn't a model's opinion — it's this highlighted span in the note, checked against a cited protocol, routed to the physician with a one-hour window. Every recommendation traces to a guideline citation and an evidence span — and a hundred percent of those spans re-verify against the note text." |
| 0:38–0:55 | Scroll to the **Trajectory** panel on the same P-1002 page. Show the per-lab trend lines (lactate falling, creatinine rising) and the green **"Gaps closed across notes"** block. | "And it isn't a snapshot — it's a trajectory. Reading this patient's prior notes, lactate is clearing, four-point-one down to three-point-one, while creatinine is climbing — so we watch the kidney. And this green block is the part that keeps the board honest: two sepsis-bundle steps that were open in an earlier note are documented now. The system tells never-done apart from done-and-resolved, so it stops nagging about work already finished. None of this touches the classifier — it reads only the current note." |
| 0:55–1:06 | Navigate to `/p/P-1041` (GIB on apixaban). Scroll to the **Medication interactions** block: red "Anticoagulant with active GI bleeding signs" flag, meds chips, citation line. | "Same idea for medication safety: thirteen citation-backed interaction rules. Apixaban plus documented GI bleeding gets a red flag, a pharmacist-voiced recommendation, and the literature citation — straight to the pharmacist's queue." |
| 1:06–1:42 | `/sandbox` (Triage sandbox). The empty state reads **"Deterministic pipeline. No LLM in the recommendation path."** — let it sit for a beat. Click the **"Negation handling — sepsis with ruled-out symptoms"** sample, hit **Run pipeline**, let the staged strip play. Then point out: the **NEG**-tagged chips in stage [1] (chest pain and melena, both struck through), the ICD candidates in [2], the protocol table in [3], the decision card + highlighted note in [4], and the **ms timings footer**. | "Under the hood — and in a clinical setting this is the part that matters — there is no LLM in the recommendation path. It says so on screen, and I can prove it: paste any note, watch the real pipeline run. Stage one extracts entities — see the NEG tag: 'denies' is caught, tagged, never silently dropped. Stage two retrieves ICD-10 codes; stage three checks twelve published care pathways step by step; stage four decides, every evidence span highlighted, in a few milliseconds. Deterministic, citation-backed rules — exactly the line AIP's use-case restrictions draw around clinical decision aids, and this system holds it by construction." |
| 1:42–2:18 | `/capacity` (Capacity / What-If). Baseline census step chart + "Beds free now" KPI. In the **Scenario builder**, toggle the `dispo delay` chip (count shows 32), click **Run scenario**. The **Scenario impact** card animates; scroll to the **Freed patients** table (32 rows); flash open **Model assumptions**. | "Surfacing problems is half the job — this page turns it into a decision. Baseline: forty-eight hours of projected free beds, from a deterministic length-of-stay model. Now the what-if: resolve every discharge-and-placement hold, and run it. Thirty-two patients discharge earlier — here they are by name — and the delta grid shows exactly when those beds come back. No ML, no black box: every number traces to an assumption stated right here on the page." |
| 2:18–2:50 | `/analytics`, scroll to **08 · Model card**: 100.0% corpus accuracy, 90.9% owner routing, 176 labeled notes, per-category precision/recall/F1. Click **Show misses** → the table lists all 16 by name, miss-type **owner**, the four imaging templates (truth physician, predicted nurse). | "Is it actually right? Measured, not asserted. Against the labeled corpus: one hundred percent, one seventy-six for one seventy-six — with an honest caveat: that's four generated notes per template, so it means all forty-four bottleneck patterns are handled, not robustness to arbitrary paraphrase. Owner routing is ninety point nine, and the sixteen misses are right here by name — every one an imaging case where the corpus says physician and the engine routes the nurse to expedite the scan. A labeling call I documented instead of papering over. And a regression gate in the test suite fails any rule change that drops accuracy below ninety-seven percent." |
| 2:50–3:12 | `/p/P-1002`, **Workflow actions** section: the pre-created red action with its SLA countdown / **OVERDUE** chip. Switch to the small terminal, run `curl -X POST localhost:8001/actions/sweep`, switch back, refresh: **ESC L1** chip; click **Audit trail** to expand the event log (`sla_breach` row). Then click **▸ LIVE TICK** in the titlebar; toast summarizes admits/discharges. | "And the loop closes. Every action carries a deadline from an ops-owned policy table — sixty minutes for a red sepsis gap. This one breached, so the sweep escalates it and writes it to the audit log: every transition, every actor, on the record. Live tick advances the whole floor — discharges out, new arrivals triaged through the exact same pipeline." |
| 3:12–3:45 | The Foundry close. Preferred: your Foundry instance — Ontology Manager objects (Patient, Note, Bottleneck, Action), then the Workshop queue screen. Fallback: editor showing `foundry_export/` — `01_ontology_spec.md` object tables, `pipeline_protocol_gap_transform.py`, `03_workshop_storyboard.md`. | "Everything you just saw is built to lift. The ontology spec maps these objects one to one, the pipeline ships as a self-contained transform with the classifier as an AIP Logic function, the SLA sweep becomes an Automation, and the Workshop storyboard is this console. The same pipeline, parity-tested, lifts into Foundry unchanged. All data here is notional — no PHI anywhere. Thanks for watching — I'm [your name]." |

**Runtime: 3:45 end-to-end** (last cell ends at 3:45), the same hard
ceiling as before — the trajectory beat is paid for by tightening the
queue, capacity, and model-card beats by a couple of seconds each.

Spoken-word budget: ~610 words ≈ 3:45 at a natural 160 wpm (the beats are
timed for that pace; drop to 145 wpm and you'll need the cuts below). If
you run long, the first cuts are, in order: the provability sentence in
the P-1002 bottleneck beat ("Every recommendation traces…"), the last
sentence of the sandbox beat, and "so we watch the kidney" in the
trajectory beat.

---

## Three alternate cold opens (pick one, 0:00–0:18)

1. **The coordination line (default, used above):** "Hospitals don't
   lose beds to medicine — they lose them to coordination: the consult
   nobody chased, the antibiotic nobody documented, the placement
   nobody called."
2. **The charge-nurse line:** "Every charge nurse starts a shift with
   the same question: out of these hundred seventy-six patients, who is
   stuck, and why? Answering it today means re-reading every note. This
   screen answers it in one glance."
3. **The four-beds line:** "This floor has a hundred eighty beds and
   four of them are free. The fastest way to find the next bed isn't
   construction — it's the notes the team already wrote. This is
   Bottleneck Radar."

---

## Pre-flight checklist (do all of this BEFORE hitting record)

**State**
- [ ] Fresh DB: `cd backend && .venv/bin/python -m app.data.generate_notes && .venv/bin/python -m app.ingest`
      (re-ingest especially if you've been clicking LIVE TICK — it admits/discharges patients).
- [ ] Backend up: `uvicorn app.main:app --port 8001` (or 8000 if free).
- [ ] Frontend up: `RADAR_API=http://localhost:8001 npm run dev` (omit `RADAR_API` if backend is on 8000).
- [ ] Titlebar health badge shows `● API <n>ms`, not `API DOWN`.
- [ ] **At least 65 minutes before recording:** on `/p/P-1002`, in
      **Workflow actions**, click **"+ Create action from recommendation"**.
      It inherits `missing_soc` / red → a 60-minute SLA, so it has breached
      by showtime and the OVERDUE chip + sweep beat work live. Verify the
      chip says OVERDUE before you record.
- [ ] Do NOT run `/actions/sweep` beforehand — the on-camera sweep needs the breach unescalated.
- [ ] On `/p/P-1002`, confirm the **Trajectory** panel renders (not the
      "single snapshot" empty state): lactate clearing, creatinine
      worsening, and the green "Gaps closed across notes" block with two
      sepsis-bundle steps. The priors load with `generate_notes` + `ingest`;
      if the panel is empty you skipped the re-ingest above.
- [ ] Sanity-pass each number on screen vs. script: census 176/180,
      dispo chip count 32, model card 100.0% / 90.9% / 176, audit corpus
      summary `pct_verified` 100.0 (`curl -s localhost:8001/audit/corpus/summary`).

**Browser**
- [ ] One window, exactly these tabs, in order:
      1. `/dashboard`  2. `/p/P-1002`  3. `/p/P-1041`  4. `/sandbox`
      5. `/capacity`  6. `/analytics`  7. Foundry (Workshop app) or editor with `foundry_export/`
- [ ] Browser zoom 110–125% so table text is legible at 1080p; hide bookmarks bar; close every other window.
- [ ] Small terminal pre-positioned (bottom corner, big font) with the
      sweep command already typed: `curl -X POST localhost:8001/actions/sweep`
- [ ] Editor font ≥ 16pt if using the `foundry_export/` fallback close.
- [ ] Notifications off (macOS Focus mode). Clock/menubar clutter hidden if possible.

**Recording**
- [ ] 1080p minimum, system audio off, decent mic, quiet room.
- [ ] Do one full silent run-through of the click path first — the
      sandbox staged animation and the capacity scenario each take a
      couple of seconds; rehearse the timing of your lines against them.
- [ ] Record the whole thing in one take if you can; viewers can tell.

---

## Fallback notes (when something is slow or weird, live)

- **Any API call is slow:** keep talking — every beat's narration works
  over a spinner. The pipeline itself is single-digit ms; slowness is
  almost always the dev server warming up. Click through each page once
  before recording so everything is warm.
- **Capacity number differs from "+32 by 24h":** read what the
  Scenario-impact card actually says. The model rolls discharges
  outside the 08:00–20:00 **UTC** window to the next morning, so an
  evening (Pacific) recording can shift the gain to the 12h/48h
  checkpoints. The freed-patients count is always 32 — "thirty-two
  patients discharge earlier" is the safe spoken line. Recording before
  ~1pm Pacific keeps "+32 by 24h" on screen.
- **OVERDUE chip didn't breach in time:** skip the sweep, point at the
  live countdown chip instead, and say "the sweep escalates anything
  past deadline and writes it to this audit log" while expanding the
  audit trail. The beat still lands.
- **Sandbox sample misfires after edits:** the samples endpoint only
  serves notes that demonstrably reproduce their category — if a sample
  looks wrong you have a stale DB; re-ingest (see pre-flight).
- **LIVE TICK toast disappears too fast:** the click also visibly
  changes the queue counts; say the line over the refreshed `/dashboard`.
- **Clicking the path live feels shaky:** drive the tour with StoryMode
  instead — `Shift+S` (or `★ STORY` in the titlebar) starts it, `→`/Space
  advance, `Esc` exits. It navigates and highlights each beat for you in
  the same order as the shot list, so you only have to narrate. Hit `p`
  if you want it to auto-advance.
- **Trajectory panel shows "single snapshot":** P-1002's prior notes
  didn't load — re-ingest (see pre-flight). Don't fake it; if it's empty
  on the day, skip the trajectory beat and add its ~17 seconds back to the
  capacity or model-card beat.
- **Total disaster (backend dies mid-take):** stop, restart uvicorn,
  re-record from the start of the current beat; each beat opens on a
  page load, so takes splice cleanly at beat boundaries.
