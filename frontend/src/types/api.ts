export type Urgency = "red" | "amber" | "green";

export interface PatientSummary {
  id: string;
  age: number;
  sex: "M" | "F";
  chief_complaint: string;
  arrival_time: string;
  primary_category: string;
  primary_label: string;
  primary_urgency: Urgency;
  primary_owner: string;
  primary_action: string;
  open_actions: number;
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
}

export interface PatientDetail {
  id: string;
  age: number;
  sex: "M" | "F";
  chief_complaint: string;
  arrival_time: string;
  note_text: string;
  primary: Bottleneck;
  secondary: Bottleneck[];
  silent_failures: SilentFailure[];
  protocol_matches: ProtocolMatch[];
  icd_candidates: ICDCandidate[];
  extraction: Extraction;
  actions: ActionItem[];
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
