export type Urgency = "red" | "amber" | "green";

export interface PatientSummary {
  id: string;
  age: number;
  sex: "M" | "F";
  chief_complaint: string;
  arrival_time: string;
  room?: string | null;
  primary_category: string;
  primary_label: string;
  primary_urgency: Urgency;
  primary_owner: string;
  primary_action: string;
  open_actions: number;
  overdue_actions: number;
  silent_failure_count: number;
}

export interface Span {
  start: number;
  end: number;
  text: string;
}

export interface Bottleneck {
  category: string;
  label: string;
  urgency: Urgency;
  owner: string;
  recommended_action: string;
  rationale: string;
  evidence: Span[];
  citation: string | null;
}

export interface SilentFailure {
  protocol_key: string;
  protocol_name: string;
  missing_action: string;
  severity: string;
  citation: string;
  trigger_evidence: Span;
  owner: string;
  urgency: Urgency;
}

export interface ProtocolMatch {
  protocol_key: string;
  protocol_name: string;
  triggered: boolean;
  documented: string[];
  missing: string[];
  trigger_evidence: Span[];
  citation: string;
  time_window_hours: number;
}

export interface ICDCandidate {
  code: string;
  description: string;
  score: number;
  category: string;
}

export interface ActionItem {
  id: number;
  patient_id: string;
  title: string;
  description: string;
  owner: string;
  urgency: Urgency;
  status: "open" | "in_progress" | "resolved" | "escalated";
  source_category: string;
  created_at: string;
  updated_at: string;
  sla_minutes: number | null;
  due_at: string | null;
  escalation_level: number;
  overdue: boolean;
  minutes_remaining: number | null;
}

export interface Finding {
  kind: string;
  label: string;
  value: string | null;
  evidence: Span;
  metadata: Record<string, string>;
}

export interface Extraction {
  vitals: Finding[];
  labs: Finding[];
  meds: Finding[];
  consults: Finding[];
  imaging: Finding[];
  dispo: Finding[];
  symptoms: Finding[];
  risk_factors: Finding[];
  code_status?: Finding[];
  mobility?: Finding[];
  pain?: Finding[];
  advance_directives?: Finding[];
  social?: Finding[];
}

// ── Longitudinal trends (patient detail) ────────────────────────────────

export interface TrendPoint {
  hours_ago: number;
  captured_at: string | null;
  value: number | null;
  raw: string | null;
  negated: boolean;
}

export interface LabTrend {
  label: string;
  polarity: "down_good" | "up_good" | "context";
  direction: "rising" | "falling" | "stable" | "insufficient";
  clinical: "improving" | "worsening" | "stable" | "unknown";
  delta: number | null;
  narrative: string;
  points: TrendPoint[];
}

export interface ResolvedGap {
  protocol_key: string;
  protocol_name: string;
  action_label: string;
  opened_seq: number;
  closed_seq: number;
}

export interface Recurrence {
  ordinal: number;
  window_phrase: string;
  evidence: string;
}

export type TrajectorySignal = "worsening" | "improving" | "mixed" | "stable" | "none";

export interface TrendsPayload {
  labs: LabTrend[];
  recurrence: Recurrence | null;
  resolved_gaps: ResolvedGap[];
  trajectory_signal: TrajectorySignal;
  note_count: number;
}

export interface PatientDetail {
  id: string;
  age: number;
  sex: "M" | "F";
  chief_complaint: string;
  arrival_time: string;
  room?: string | null;
  note_text: string;
  primary: Bottleneck;
  secondary: Bottleneck[];
  silent_failures: SilentFailure[];
  protocol_matches: ProtocolMatch[];
  icd_candidates: ICDCandidate[];
  extraction: Extraction;
  actions: ActionItem[];
  trends?: TrendsPayload | null;
}

export interface FloorBed {
  room: string;
  wing: string;
  bed_number: number;
  patient_id?: string | null;
  urgency?: Urgency | null;
  primary_category?: string | null;
  primary_owner?: string | null;
  chief_complaint?: string | null;
  age?: number | null;
  sex?: "M" | "F" | null;
  open_actions: number;
}

export interface FloorMap {
  wings: string[];
  beds_per_wing: number;
  beds: FloorBed[];
}

export interface ProtocolGapBreakdown {
  protocol_key: string;
  protocol_name: string;
  total_triggered: number;
  total_gaps: number;
  missing_by_action: Record<string, number>;
}

export interface Analytics {
  total_patients: number;
  by_urgency: Record<string, number>;
  by_category: Record<string, number>;
  by_owner: Record<string, number>;
  by_protocol: ProtocolGapBreakdown[];
  arrival_age_buckets: Record<string, number>;
  action_status: Record<string, number>;
  actions_per_owner: Record<string, number>;
  silent_failures_by_protocol: Record<string, number>;
}

export interface TimelineEvent {
  timestamp: string;
  kind: "arrival" | "triage" | "gap_detected" | "action_created" | "action_state" | "note" | "prior_note";
  title: string;
  detail?: string | null;
  urgency?: Urgency | null;
  actor?: string | null;
}

export interface PatientTimeline {
  patient_id: string;
  events: TimelineEvent[];
}

export interface ActionEventItem {
  id: number;
  action_id: number;
  event_type: string;
  from_value?: string | null;
  to_value?: string | null;
  actor: string;
  note?: string | null;
  created_at: string;
}

export interface HandoffSection {
  title: string;
  patient_id?: string | null;
  room?: string | null;
  urgency?: Urgency | null;
  bullets: string[];
}

export interface HandoffReport {
  generated_at: string;
  shift_label: string;
  floor: string;
  summary: Record<string, number>;
  critical: HandoffSection[];
  open_protocol_gaps: HandoffSection[];
  awaiting_dispo: HandoffSection[];
  open_actions_by_owner: Record<string, HandoffSection[]>;
}

export interface WhyStuck {
  patient_id: string;
  summary: string;
  bullet_points: string[];
  primary: Bottleneck;
  contributing: Bottleneck[];
  silent_failures: SilentFailure[];
}

export interface Stats {
  total_patients: number;
  by_urgency: Record<string, number>;
  by_category: Record<string, number>;
  by_owner: Record<string, number>;
  open_actions: number;
  silent_failures: number;
  median_arrival_age_hours: number;
}

// ── Capacity forecast / what-if simulation ──────────────────────────────

export interface CensusPoint {
  hour_offset: number;
  projected_census: number;
  projected_discharges_cum: number;
  projected_admissions_cum: number;
  projected_free: number;
}

export interface WingCapacity {
  wing: string;
  beds_total: number;
  occupied: number;
  free: number;
  projected_discharges_24h: number;
}

export interface ModelAssumption {
  key: string;
  label: string;
  value: string;
  rationale: string;
}

export interface CapacityForecast {
  anchor: string;
  horizon_hours: number;
  beds_total: number;
  census_now: number;
  series: CensusPoint[];
  wings: WingCapacity[];
  assumptions: ModelAssumption[];
}

export interface FreedPatient {
  patient_id: string;
  room: string | null;
  category: string;
  urgency: Urgency;
  baseline_eta_hours: number;
  scenario_eta_hours: number;
  gained_hours: number;
}

export interface CapacitySimulation {
  anchor: string;
  horizon_hours: number;
  beds_total: number;
  baseline: CensusPoint[];
  scenario: CensusPoint[];
  freed: FreedPatient[];
  delta_free_beds: Record<string, number>;
  assumptions: ModelAssumption[];
}

// ── Triage sandbox ──────────────────────────────────────────────────────

export interface SandboxTriage {
  primary: Bottleneck;
  secondary: Bottleneck[];
  silent_failures: SilentFailure[];
  protocol_matches: ProtocolMatch[];
}

export interface SandboxResult {
  triage: SandboxTriage;
  extraction: Extraction;
  icd_candidates: ICDCandidate[];
  stage_timings_ms: {
    extract: number;
    classify: number;
    icd: number;
    total: number;
  };
  engine: {
    protocols_evaluated: number;
    categories: number;
    version: string;
  };
}

export interface SandboxSample {
  key: string;
  label: string;
  note_text: string;
  expected_category: string;
}

// ── Eval / model card ───────────────────────────────────────────────────

export interface EvalCategoryMetrics {
  category: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface EvalConfusionCell {
  truth: string;
  predicted: string;
  count: number;
}

export interface EvalSummary {
  n: number;
  accuracy: number;
  per_category: EvalCategoryMetrics[];
  confusion: EvalConfusionCell[];
  owner_routing: { n: number; accuracy: number };
}

export interface EvalMiss {
  patient_id: string;
  miss_type: "category" | "owner";
  truth: string;
  predicted: string;
  urgency: Urgency;
  template_name: string | null;
}

// ── Drug interactions ───────────────────────────────────────────────────

export interface InteractionMed {
  name: string;
  class: string;
  evidence: Span;
}

export interface InteractionFlag {
  rule_key: string;
  name: string;
  severity: "red" | "amber";
  mechanism: string;
  recommendation: string;
  citation: string;
  meds_involved: InteractionMed[];
  context_evidence: Span[];
}

export interface PatientInteractions {
  patient_id: string;
  flags: InteractionFlag[];
}

// ── Live floor tick ─────────────────────────────────────────────────────

export interface TickResult {
  admitted: { patient_id: string; room: string; category: string; urgency: Urgency }[];
  discharged: { patient_id: string; room: string | null }[];
  actions_progressed: { action_id: number; from: string; to: string }[];
  census_after: number;
  tick_minutes: number;
}

export interface SimStatus {
  census: number;
  beds_total: number;
  beds_free: number;
  open_actions: number;
  clear_patients: number;
}

// ── SLA sweep ───────────────────────────────────────────────────────────

export interface SweepResult {
  checked: number;
  breached: number;
  escalated_ids: number[];
}

export interface BulkUpdateResult {
  updated: ActionItem[];
  missing: number[];
  skipped: { id: number; reason: string }[];
}

// ── Census time-series + finalized handoff snapshots ────────────────────

export interface CensusPointOut {
  captured_at: string;
  census: number;
  red: number;
  amber: number;
  green: number;
  open_actions: number;
  overdue_actions: number;
  silent_failures: number;
  source: string;
}

export interface CensusSeries {
  points: CensusPointOut[];
  n: number;
}

export interface HandoffSnapshotMeta {
  id: number;
  captured_at: string;
  shift_label: string;
  finalized_by: string;
}

export interface HandoffHistory {
  snapshots: HandoffSnapshotMeta[];
  n: number;
}
