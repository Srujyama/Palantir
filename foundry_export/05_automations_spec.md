# Automations spec — closing the loop in Foundry

Four **Foundry Automations** (object monitors + scheduled triggers) that
turn the static classification into a living operational loop. Each one is a
1:1 lift of a behavior that already runs locally — the local endpoint is
named under every automation so a reviewer can diff the semantics against
working code.

All four are deterministic: no model call anywhere in any effect. Every
effect that mutates state writes an `ActionEvent` audit row, same as the
local backend (`app/api/actions.py`).

---

## Shared policy: the SLA table

Single source of truth for "how long does the floor have to act?". Locally
this is `backend/app/services/sla.py`; in Foundry it should live as a small
versioned **ontology object set** (`SlaPolicy`) with operational sign-off,
so throughput leads tune it without touching code. Lookup order: exact
(category, urgency) → category wildcard `*` → default.

| (source_category, urgency) | sla_minutes | derivation |
|----------------------------|-------------|------------|
| missing_soc, red           | 60          | 1h bundles: sepsis hour-1, stroke, neutropenic fever, hyperkalemia (`time_window_hours=1` in the protocol library) |
| missing_soc, amber         | 240         | 4-6h bundles: COPD (4h), CAP (6h); 240 is the conservative bound |
| med_risk, red              | 60          | active patient-safety exposure |
| med_risk, amber            | 120         | safety review within a nursing shift block |
| awaiting_consult, *        | 240         | page + 30-min escalation ladder, x2 retries |
| awaiting_imaging, *        | 180         | radiology expedite window |
| readmit_risk, *            | 720         | transitional-care setup, half a day |
| dispo_delay, *             | 1440        | placement / auth work, one business day |
| (anything else)            | 480         | default: one 8h shift |

---

## Automation (a) — New red Bottleneck → notify + auto-create Action

Mirrors locally: **`POST /actions/{patient_id}`** (SLA stamped at create via
the policy table) and the Workshop "+ Create action from recommendation"
button. The automation is that button, pressed by the platform the moment a
red appears instead of waiting for someone to look at the queue.

| Field | Value |
|---|---|
| **Trigger** | Object monitor on `Bottleneck`: object added, or `urgency` property transitions to `red` |
| **Condition** | `urgency == "red"` AND no existing `Action` for this `patient_id` with the same `bottleneck_category` in status `open` / `in_progress` / `escalated` |
| **Effect** | (1) Apply `create-coordination-action`: `title = Bottleneck.recommended_action`, `owner_role = Bottleneck.owner`, `status = "open"`, `due_at = now + sla_minutes(category, "red")`. (2) Notify the owner-role group (physician / pharmacist / nurse / case_manager) with patient_id, evidence span, and citation. |
| **Rate limits / dedupe** | One open Action per (patient_id, category) — the condition is the dedupe. Suppress repeat notifications for the same Bottleneck within its SLA window. Cap at 20 auto-creates per run as a runaway guard (a full-floor red spike should page a human, not file 176 tickets). |
| **Monitoring metric** | **Time-to-acknowledge**: minutes from Action creation to `in_progress`, split by owner role. Secondary: count of auto-created reds per shift (a rising trend means an upstream documentation problem, not a tooling problem). |

---

## Automation (b) — Action open past `due_at` → escalate + audit event

Mirrors locally: **`POST /actions/sweep`** — idempotent breach sweep,
verbatim semantics. Locally it's an endpoint so the demo is deterministic
and inspectable; in Foundry it's the schedule that endpoint stands in for.

| Field | Value |
|---|---|
| **Trigger** | Scheduled, every 15 minutes |
| **Condition** | `Action.status` in {`open`, `in_progress`} AND `now > due_at` (`escalated` and `resolved` are excluded — already-escalated actions are never re-escalated, resolved work is never overdue) |
| **Effect** | Set `status = "escalated"`, increment `escalation_level`, write `ActionEvent(event_type="sla_breach", actor="sla-sweep", note="SLA breached: N min past due (window M min for category/urgency); escalation level L")`, notify the owner role and the charge nurse |
| **Rate limits / dedupe** | Idempotent by construction: the status flip removes the row from the next sweep's candidate set, so each breach escalates and logs exactly once. No further cap needed. |
| **Monitoring metric** | **Breach rate per shift** (breached / created) and **mean minutes overdue at escalation**. If the mean is high, the sweep interval or the notification path is too slow; if the rate is high, the SLA table needs operational re-tuning — that's why it's an editable object set. |

---

## Automation (c) — Scheduled re-evaluation (re-materialize urgency)

Mirrors locally: the pipeline rerun semantics — **`POST /simulate/tick`**
pushes every admitted/progressed patient back through the exact same
`pipeline.run()` path (extract → classify → persist Triage), and the
sandbox (`POST /sandbox/triage`) runs it ad hoc. The rerun is safe because
`classify_bottleneck` is pure: same note in, same Bottleneck out.

| Field | Value |
|---|---|
| **Trigger** | Two: (1) object monitor on `Note` — `note_text` changed or Note added; (2) scheduled hourly backstop across the census |
| **Condition** | None beyond the trigger — re-evaluation is idempotent, so it is always safe to run |
| **Effect** | Invoke the `classify_bottleneck` Function for each affected patient and upsert the `Bottleneck` object (one active Bottleneck per patient, keyed on `patient_id`). Downstream, automation (a) fires if a new red materialized. |
| **Why this matters** | Urgency is a function of the note, and notes change: a stroke note gains "window expired", a sepsis note gains "antibiotics started", a COPD note gains "resolved". Without re-evaluation the board shows yesterday's urgency. With it, resolution phrases *clear* bottlenecks and new documentation gaps *raise* them — both directions, automatically. |
| **Rate limits / dedupe** | Debounce per patient: at most one re-evaluation per patient per 5 minutes (notes are edited in bursts). The hourly backstop runs the full census; at 176 notes the function is single-digit milliseconds per note, so cost is negligible. |
| **Monitoring metric** | **Staleness**: max age of `Bottleneck` recompute timestamp across the census (alert if > 2h). Secondary: **category churn per run** — how many patients changed category; sudden spikes mean a note-source ingestion problem upstream. |

---

## Automation (d) — Handoff snapshot at shift boundaries

Mirrors locally: **`GET /handoff`** — the shift handoff report (critical
patients, protocol gaps with citations, dispo holds, open actions grouped by
owner). Locally the day/night boundary is 07:00 / 19:00
(`app/api/handoff.py`); the automation pins the snapshot to those moments so
the off-going and on-coming charge nurses see the same frozen board.

| Field | Value |
|---|---|
| **Trigger** | Scheduled: 07:00 and 19:00 local, daily |
| **Condition** | None — the handoff happens every shift regardless of floor state; an empty section is itself information |
| **Effect** | Materialize a `HandoffSnapshot` dataset row (timestamp, shift label, sections: critical / protocol gaps / dispo holds / open actions by owner — each bullet carrying patient_id, room, owner, citation), and send it as a notification to the unit group. Render printable from Workshop, same as the local print mode. |
| **Rate limits / dedupe** | Two per day by construction. Keyed on (date, shift) so a retried run overwrites rather than duplicates. |
| **Monitoring metric** | **Open reds crossing the boundary** and **escalations unacknowledged at handoff** — the two numbers an off-going charge nurse is accountable for. Trend them week over week; the whole product exists to push both toward zero. |

---

## What runs where (same line as the pipeline spec)

| Step | Runs in | Model involved? |
|---|---|---|
| (a) red → notify + Action | Automation + Action Type | No |
| (b) breach → escalate | Scheduled automation | No |
| (c) re-evaluation | Automation → `classify_bottleneck` Function | No |
| (d) handoff snapshot | Scheduled automation → dataset + notification | No |

**No LLM is in any automation path.** Notifications quote the
deterministic `summary`, `evidence_span`, and `citation` properties as-is.
The conversational layer (`04_aip_agent_spec.md`) reads the same objects but
never feeds these automations.

---

## What NOT to automate

- Don't auto-**resolve** actions on re-evaluation. If automation (c) clears
  a Bottleneck, the open Action stays open for a human to resolve — the
  audit trail must show a person confirmed the work happened, not that a
  regex stopped matching.
- Don't auto-create actions for amber/green — that's queue noise. Ambers
  surface on the board and in the handoff; only reds page someone.
- Don't let any automation edit `Patient` or `Note` (read-only sources,
  same rule as the Workshop spec).
