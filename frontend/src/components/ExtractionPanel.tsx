import type { Extraction } from "../types/api";

function block(label: string, items: { label: string; value?: string | null; meta?: string }[]) {
  if (!items.length) {
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 10,
          textTransform: "uppercase", letterSpacing: "0.1em",
          color: "var(--fg-3)", marginBottom: 4,
        }}>{label}</div>
        <div style={{ color: "var(--fg-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>—</div>
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 10,
        textTransform: "uppercase", letterSpacing: "0.1em",
        color: "var(--fg-3)", marginBottom: 6,
      }}>{label}</div>
      <div className="entities">
        {items.map((it, i) => (
          <span key={i} className="tag" title={it.meta}>
            {it.label}{it.value ? <span style={{ color: "var(--fg-2)", marginLeft: 4 }}>{it.value}</span> : null}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ExtractionPanel({ ext }: { ext: Extraction }) {
  const hasContext =
    (ext.code_status?.length ?? 0) > 0
    || (ext.mobility?.length ?? 0) > 0
    || (ext.pain?.length ?? 0) > 0
    || (ext.advance_directives?.length ?? 0) > 0
    || (ext.social?.length ?? 0) > 0;
  return (
    <div>
      {block("Vitals", ext.vitals.map((f) => ({ label: f.label, value: f.value })))}
      {block("Labs", ext.labs.map((f) => ({ label: f.label, value: f.value })))}
      {block("Medications", ext.meds.map((f) => ({
        label: f.label,
        meta: f.metadata?.class,
      })))}
      {block("Symptoms", ext.symptoms.map((f) => ({ label: f.label.replace(/_/g, " ") })))}
      {block("Consults", ext.consults.map((f) => ({ label: f.label, value: f.value ?? undefined })))}
      {block("Imaging", ext.imaging.map((f) => ({ label: f.label.toUpperCase(), value: f.value ?? undefined })))}
      {block("Dispo signals", ext.dispo.map((f) => ({ label: f.label.replace(/_/g, " ") })))}
      {block("Risk markers", ext.risk_factors.map((f) => ({ label: f.label.replace(/_/g, " ") })))}
      {hasContext && (
        <>
          {block("Code status", (ext.code_status ?? []).map((f) => ({ label: f.label.replace(/_/g, " ") })))}
          {block("Mobility", (ext.mobility ?? []).map((f) => ({ label: f.label.replace(/_/g, " ") })))}
          {block("Pain", (ext.pain ?? []).map((f) => ({ label: f.label.replace(/_/g, " "), value: f.value ?? undefined })))}
          {block("Advance directives", (ext.advance_directives ?? []).map((f) => ({ label: f.label.replace(/_/g, " ") })))}
          {block("Social context", (ext.social ?? []).map((f) => ({ label: f.label.replace(/_/g, " ") })))}
        </>
      )}
    </div>
  );
}
