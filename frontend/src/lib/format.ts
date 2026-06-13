export function hoursAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const h = (now - then) / 3_600_000;
  if (h < 1) return `${Math.max(0, Math.round(h * 60))}m`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Format a (positive) minute count as a compact duration: 45m, 2h 30m, 1.5d */
export function fmtMinutes(mins: number): string {
  const m = Math.max(0, Math.round(mins));
  if (m < 90) return `${m}m`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h < 48) return r > 0 ? `${h}h ${r}m` : `${h}h`;
  return `${(m / 1440).toFixed(1)}d`;
}

const OWNER_DISPLAY: Record<string, string> = {
  physician: "Physician",
  nurse: "Charge nurse",
  pharmacist: "Pharmacist",
  case_manager: "Case manager",
  social_worker: "Social worker",
  "": "—",
};

export function ownerLabel(owner: string): string {
  return OWNER_DISPLAY[owner] ?? owner;
}

const CATEGORY_SHORT: Record<string, string> = {
  missing_soc: "MISSING SOC",
  med_risk: "MED RISK",
  awaiting_consult: "AWAIT CONSULT",
  awaiting_imaging: "AWAIT IMAGING",
  dispo_delay: "DISPO",
  readmit_risk: "READMIT RISK",
  clear: "CLEAR",
};

export function categoryShort(c: string): string {
  return CATEGORY_SHORT[c] ?? c.toUpperCase();
}
