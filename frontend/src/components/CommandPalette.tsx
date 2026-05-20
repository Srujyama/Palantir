import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { PatientSummary } from "../types/api";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  kind: "nav" | "patient" | "filter" | "action";
  perform: () => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
    if (open && patients.length === 0) {
      void api.patients({}).then(setPatients).catch(() => undefined);
    }
  }, [open]);

  const items = useMemo<CommandItem[]>(() => {
    const nav: CommandItem[] = [
      { id: "q", label: "Go to Queue", hint: "G then Q", kind: "nav", perform: () => navigate("/dashboard") },
      { id: "f", label: "Go to Floor Map", hint: "G then F", kind: "nav", perform: () => navigate("/floor") },
      { id: "a", label: "Go to Analytics", hint: "G then A", kind: "nav", perform: () => navigate("/analytics") },
      { id: "h", label: "Go to Handoff", hint: "G then H", kind: "nav", perform: () => navigate("/handoff") },
      { id: "l", label: "Back to Landing", hint: "G then L", kind: "nav", perform: () => navigate("/") },
    ];
    const filters: CommandItem[] = [
      { id: "fr", label: "Filter: critical only", hint: "queue", kind: "filter", perform: () => navigate("/dashboard?urgency=red") },
      { id: "fa", label: "Filter: elevated only", hint: "queue", kind: "filter", perform: () => navigate("/dashboard?urgency=amber") },
      { id: "fg", label: "Filter: routine only", hint: "queue", kind: "filter", perform: () => navigate("/dashboard?urgency=green") },
      { id: "fp", label: "Filter: physician owner", kind: "filter", perform: () => navigate("/dashboard?owner=physician") },
      { id: "fn", label: "Filter: nurse owner", kind: "filter", perform: () => navigate("/dashboard?owner=nurse") },
      { id: "fc", label: "Filter: case-manager owner", kind: "filter", perform: () => navigate("/dashboard?owner=case_manager") },
      { id: "fph", label: "Filter: pharmacist owner", kind: "filter", perform: () => navigate("/dashboard?owner=pharmacist") },
    ];
    const patientNav: CommandItem[] = patients.map((p) => ({
      id: `p-${p.id}`,
      label: `${p.id} · ${p.chief_complaint}`,
      hint: `${p.room ?? "—"} · ${p.primary_urgency}`,
      kind: "patient",
      perform: () => navigate(`/p/${p.id}`),
    }));
    return [...nav, ...filters, ...patientNav];
  }, [navigate, patients]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.label.toLowerCase().includes(q) || (i.hint ?? "").toLowerCase().includes(q));
  }, [items, query]);

  useEffect(() => {
    setCursor(0);
  }, [query, open]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(filtered.length - 1, c + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = filtered[cursor];
      if (item) {
        item.perform();
        setOpen(false);
        setQuery("");
      }
    }
  };

  if (!open) return null;

  return (
    <div className="cmdp-backdrop" onClick={() => setOpen(false)}>
      <div className="cmdp" onClick={(e) => e.stopPropagation()}>
        <div className="cmdp-input-row">
          <span className="cmdp-prompt">›</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Jump to patient, page, or filter…"
            className="cmdp-input"
          />
          <span className="cmdp-hint">↑↓ navigate · ↵ select · esc close</span>
        </div>
        <div className="cmdp-results">
          {filtered.slice(0, 30).map((item, i) => (
            <div
              key={item.id}
              className={`cmdp-item ${i === cursor ? "active" : ""}`}
              onMouseEnter={() => setCursor(i)}
              onClick={() => {
                item.perform();
                setOpen(false);
                setQuery("");
              }}
            >
              <span className={`cmdp-kind cmdp-kind-${item.kind}`}>{item.kind}</span>
              <span className="cmdp-label">{item.label}</span>
              {item.hint && <span className="cmdp-item-hint mono">{item.hint}</span>}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="cmdp-empty">No matches.</div>
          )}
        </div>
      </div>
    </div>
  );
}
