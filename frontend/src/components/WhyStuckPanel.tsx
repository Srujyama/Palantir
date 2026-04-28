import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { WhyStuck } from "../types/api";

export function WhyStuckPanel({ patientId }: { patientId: string }) {
  const [data, setData] = useState<WhyStuck | null>(null);
  const [loading, setLoading] = useState(false);
  const [opened, setOpened] = useState(false);

  useEffect(() => {
    setData(null); setOpened(false);
  }, [patientId]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.whyStuck(patientId);
      setData(r);
      setOpened(true);
    } finally {
      setLoading(false);
    }
  };

  if (!opened) {
    return (
      <button className="btn primary" onClick={load} disabled={loading}>
        {loading ? "REASONING…" : "Why is this patient stuck?"}
      </button>
    );
  }
  if (!data) return null;
  return (
    <div className="why-panel">
      <div className="summary">{data.summary}</div>
      <ul>
        {data.bullet_points.map((b, i) => <li key={i}>{b}</li>)}
      </ul>
    </div>
  );
}
