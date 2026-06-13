import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import type { PatientSummary, Stats } from "../types/api";
import { Sidebar } from "../components/Sidebar";
import { KpiStrip } from "../components/KpiStrip";
import { PatientTable } from "../components/PatientTable";

interface Filter {
  urgency?: string;
  owner?: string;
  category?: string;
  search?: string;
}

const OWNERS = ["physician", "nurse", "pharmacist", "case_manager"] as const;
type Owner = (typeof OWNERS)[number];

export function QueuePage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [stats, setStats] = useState<Stats | null>(null);
  const [rows, setRows] = useState<PatientSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cursor, setCursor] = useState(0);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkOwner, setBulkOwner] = useState<Owner>("case_manager");
  const [bulkTitle, setBulkTitle] = useState("Coordinate next step");
  const [bulkDesc, setBulkDesc] = useState("Created via bulk coordination from queue.");
  const [bulkUrgency, setBulkUrgency] = useState<"red" | "amber" | "green">("amber");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filter: Filter = useMemo(() => ({
    urgency: params.get("urgency") ?? undefined,
    owner: params.get("owner") ?? undefined,
    category: params.get("category") ?? undefined,
    search: params.get("q") ?? undefined,
  }), [params]);

  const setFilter = (f: Filter) => {
    const p = new URLSearchParams();
    if (f.urgency) p.set("urgency", f.urgency);
    if (f.owner) p.set("owner", f.owner);
    if (f.category) p.set("category", f.category);
    if (f.search) p.set("q", f.search);
    setParams(p, { replace: true });
  };

  const reload = async () => {
    try {
      const [s, p] = await Promise.all([api.stats(), api.patients(filter)]);
      setStats(s);
      setRows(p);
      setError(null);
      setCursor((c) => Math.min(Math.max(0, c), Math.max(0, p.length - 1)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => { void reload(); /* eslint-disable-line */ }, [JSON.stringify(filter)]);

  // Titlebar live-tick button dispatches "radar:refresh" — reload in place.
  useEffect(() => {
    const onRefresh = () => { void reload(); };
    window.addEventListener("radar:refresh", onRefresh);
    return () => window.removeEventListener("radar:refresh", onRefresh);
    // eslint-disable-next-line
  }, [JSON.stringify(filter)]);

  // Keyboard nav: j/k cursor, enter to open, x to select
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      // When the bulk-action modal is open, let Escape close it but don't let
      // j/k/x/Enter drive the (hidden) table cursor or navigate away and lose
      // the half-filled form.
      if (bulkOpen) {
        if (e.key === "Escape") {
          setSelected(new Set());
          setBulkOpen(false);
        }
        return;
      }
      if (rows.length === 0) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setCursor((c) => Math.min(rows.length - 1, c + 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) => Math.max(0, c - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        navigate(`/p/${rows[cursor].id}`);
      } else if (e.key === "x") {
        e.preventDefault();
        const id = rows[cursor].id;
        toggleSelect(id);
      } else if (e.key === "Escape") {
        setSelected(new Set());
        setBulkOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, navigate, bulkOpen]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const clearSelection = () => setSelected(new Set());

  const onBulkCreate = async () => {
    if (selected.size === 0) return;
    setSubmitting(true);
    try {
      await api.bulkCreateActions({
        patient_ids: Array.from(selected),
        title: bulkTitle,
        description: bulkDesc,
        owner: bulkOwner,
        urgency: bulkUrgency,
        source_category: "queue_bulk",
      });
      setBulkOpen(false);
      clearSelection();
      await reload();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app-body">
      <Sidebar
        stats={stats}
        filter={{ urgency: filter.urgency, owner: filter.owner, category: filter.category }}
        onFilter={(f) => setFilter({ ...filter, ...f })}
      />
      <div className="main">
        <KpiStrip stats={stats} />
        <div className="toolbar">
          <input
            className="search-input"
            placeholder="Search patient ID, room, or chief complaint…"
            value={filter.search ?? ""}
            onChange={(e) => setFilter({ ...filter, search: e.target.value })}
          />
          {selected.size > 0 && (
            <div className="bulk-bar">
              <span className="bulk-count">{selected.size} selected</span>
              <button className="btn primary" onClick={() => setBulkOpen(true)}>Create action for {selected.size}</button>
              <button className="btn" onClick={clearSelection}>Clear</button>
            </div>
          )}
          <div className="spacer" />
          <span className="count">{rows.length} ROWS</span>
        </div>
        {error && (
          <div style={{ padding: "var(--s-3) var(--s-5) 0" }}>
            <div className="error-strip">
              <span>Queue load failed: {error}</span>
              <button className="btn" onClick={() => void reload()}>Retry</button>
            </div>
          </div>
        )}
        <PatientTable
          rows={rows}
          selected={selected}
          onToggleSelect={toggleSelect}
          cursor={cursor}
        />
      </div>

      {bulkOpen && (
        <div className="cmdp-backdrop" onClick={() => setBulkOpen(false)}>
          <div className="bulk-modal" onClick={(e) => e.stopPropagation()}>
            <div className="bulk-head">
              <div>
                <div className="anal-eyebrow">Bulk coordination</div>
                <h3>Create one action across {selected.size} patients</h3>
              </div>
              <button className="btn" onClick={() => setBulkOpen(false)}>Esc</button>
            </div>
            <div className="bulk-grid">
              <label className="bulk-field">
                <span>Title</span>
                <input value={bulkTitle} onChange={(e) => setBulkTitle(e.target.value)} />
              </label>
              <label className="bulk-field">
                <span>Owner</span>
                <select value={bulkOwner} onChange={(e) => setBulkOwner(e.target.value as Owner)}>
                  {OWNERS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </label>
              <label className="bulk-field">
                <span>Urgency</span>
                <select value={bulkUrgency} onChange={(e) => setBulkUrgency(e.target.value as "red" | "amber" | "green")}>
                  <option value="red">red</option>
                  <option value="amber">amber</option>
                  <option value="green">green</option>
                </select>
              </label>
              <label className="bulk-field bulk-field-full">
                <span>Description</span>
                <textarea rows={3} value={bulkDesc} onChange={(e) => setBulkDesc(e.target.value)} />
              </label>
            </div>
            <div className="bulk-list">
              <div className="bulk-list-label">Patients receiving this action:</div>
              <div className="bulk-list-ids">
                {Array.from(selected).map((id) => <span key={id} className="tag mono">{id}</span>)}
              </div>
            </div>
            <div className="bulk-foot">
              <button className="btn" onClick={() => setBulkOpen(false)} disabled={submitting}>Cancel</button>
              <button className="btn primary" onClick={onBulkCreate} disabled={submitting}>
                {submitting ? "Creating…" : `Create ${selected.size} actions`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
