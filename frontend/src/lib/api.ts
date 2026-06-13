import type {
  ActionEventItem,
  ActionItem,
  Analytics,
  BulkUpdateResult,
  CapacityForecast,
  CapacitySimulation,
  CensusSeries,
  EvalMiss,
  EvalSummary,
  FloorMap,
  HandoffHistory,
  HandoffReport,
  HandoffSnapshotMeta,
  PatientDetail,
  PatientInteractions,
  PatientSummary,
  PatientTimeline,
  SandboxResult,
  SandboxSample,
  SimStatus,
  Stats,
  SweepResult,
  TickResult,
  WhyStuck,
} from "../types/api";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface PatientListFilters {
  urgency?: string;
  owner?: string;
  category?: string;
  search?: string;
}

export const api = {
  patients(filters: PatientListFilters = {}): Promise<PatientSummary[]> {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v) q.set(k, v);
    });
    const qs = q.toString();
    return request<PatientSummary[]>(`/patients${qs ? `?${qs}` : ""}`);
  },
  patient(id: string): Promise<PatientDetail> {
    return request<PatientDetail>(`/patients/${id}`);
  },
  whyStuck(id: string): Promise<WhyStuck> {
    return request<WhyStuck>(`/patients/${id}/why`);
  },
  stats(): Promise<Stats> {
    return request<Stats>("/stats");
  },
  createAction(patientId: string, body: {
    title: string;
    description: string;
    owner: string;
    urgency: string;
    source_category: string;
  }): Promise<ActionItem> {
    return request<ActionItem>(`/actions/${patientId}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  updateAction(actionId: number, body: { status?: string; owner?: string }): Promise<ActionItem> {
    return request<ActionItem>(`/actions/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  actionEvents(actionId: number): Promise<ActionEventItem[]> {
    return request<ActionEventItem[]>(`/actions/${actionId}/events`);
  },
  bulkCreateActions(body: {
    patient_ids: string[];
    title: string;
    description: string;
    owner: string;
    urgency: string;
    source_category: string;
  }): Promise<ActionItem[]> {
    return request<ActionItem[]>("/actions/bulk", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  bulkUpdateActions(body: { action_ids: number[]; status?: string; owner?: string; actor?: string }): Promise<BulkUpdateResult> {
    return request<BulkUpdateResult>("/actions/bulk", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  actions(filters: { status?: string; owner?: string; overdue?: boolean } = {}): Promise<ActionItem[]> {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") q.set(k, String(v));
    });
    const qs = q.toString();
    return request<ActionItem[]>(`/actions${qs ? `?${qs}` : ""}`);
  },
  addActionNote(actionId: number, body: { note: string; actor?: string }): Promise<ActionEventItem> {
    return request<ActionEventItem>(`/actions/${actionId}/notes`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  sweepActions(): Promise<SweepResult> {
    return request<SweepResult>("/actions/sweep", { method: "POST" });
  },
  capacityForecast(horizon = 48): Promise<CapacityForecast> {
    return request<CapacityForecast>(`/capacity/forecast?horizon=${horizon}`);
  },
  capacitySimulate(body: {
    resolve_categories?: string[];
    resolve_patient_ids?: string[];
    horizon_hours?: number;
  }): Promise<CapacitySimulation> {
    return request<CapacitySimulation>("/capacity/simulate", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  sandboxTriage(body: { note_text: string; age?: number; sex?: string }): Promise<SandboxResult> {
    return request<SandboxResult>("/sandbox/triage", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  sandboxSamples(): Promise<SandboxSample[]> {
    return request<SandboxSample[]>("/sandbox/samples");
  },
  evalSummary(): Promise<EvalSummary> {
    return request<EvalSummary>("/eval/summary");
  },
  evalMisses(): Promise<EvalMiss[]> {
    return request<EvalMiss[]>("/eval/misses");
  },
  interactions(patientId: string): Promise<PatientInteractions> {
    return request<PatientInteractions>(`/patients/${patientId}/interactions`);
  },
  simulateTick(minutes = 60): Promise<TickResult> {
    return request<TickResult>("/simulate/tick", {
      method: "POST",
      body: JSON.stringify({ minutes }),
    });
  },
  simulateStatus(): Promise<SimStatus> {
    return request<SimStatus>("/simulate/status");
  },
  health(): Promise<{ status: string }> {
    return request<{ status: string }>("/health");
  },
  floor(): Promise<FloorMap> {
    return request<FloorMap>("/floor");
  },
  analytics(): Promise<Analytics> {
    return request<Analytics>("/analytics");
  },
  handoff(): Promise<HandoffReport> {
    return request<HandoffReport>("/handoff");
  },
  timeline(patientId: string): Promise<PatientTimeline> {
    return request<PatientTimeline>(`/patients/${patientId}/timeline`);
  },
  censusSeries(limit = 200): Promise<CensusSeries> {
    return request<CensusSeries>(`/census/series?limit=${limit}`);
  },
  finalizeHandoff(body: { finalized_by?: string } = {}): Promise<HandoffSnapshotMeta> {
    return request<HandoffSnapshotMeta>("/census/handoff/finalize", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  handoffHistory(): Promise<HandoffHistory> {
    return request<HandoffHistory>("/census/handoff/history");
  },
  handoffSnapshot(id: number): Promise<HandoffReport> {
    return request<HandoffReport>(`/census/handoff/${id}`);
  },
};
