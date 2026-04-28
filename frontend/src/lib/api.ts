import type {
  ActionItem,
  PatientDetail,
  PatientSummary,
  Stats,
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
};
