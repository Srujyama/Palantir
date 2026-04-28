import type { Urgency } from "../types/api";

export function UrgencyPill({ urgency }: { urgency: Urgency }) {
  const label = urgency === "red" ? "Critical" : urgency === "amber" ? "Elevated" : "Routine";
  return (
    <span className={`urgency-pill ${urgency}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
