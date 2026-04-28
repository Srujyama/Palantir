import type { ProtocolMatch } from "../types/api";

export function ProtocolTable({ matches }: { matches: ProtocolMatch[] }) {
  return (
    <table className="protocol-table">
      <thead>
        <tr>
          <th style={{ width: "30%" }}>Protocol</th>
          <th style={{ width: 80 }}>Status</th>
          <th>Documented</th>
          <th>Missing</th>
        </tr>
      </thead>
      <tbody>
        {matches.map((m) => (
          <tr key={m.protocol_key}>
            <td>
              <div style={{ color: m.triggered ? "var(--fg-0)" : "var(--fg-3)" }}>
                {m.protocol_name}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)", marginTop: 2 }}>
                {m.citation} · {m.time_window_hours}h window
              </div>
            </td>
            <td>
              {!m.triggered ? (
                <span className="dim">N/A</span>
              ) : m.missing.length === 0 ? (
                <span className="ok">COMPLETE</span>
              ) : (
                <span className="miss">GAPS&nbsp;{m.missing.length}</span>
              )}
            </td>
            <td>
              {m.documented.length === 0 ? <span className="dim">—</span> :
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {m.documented.map((d, i) => <li key={i} className="ok">{d}</li>)}
                </ul>
              }
            </td>
            <td>
              {m.missing.length === 0 ? <span className="dim">—</span> :
                <ul style={{ margin: 0, paddingLeft: 16 }}>
                  {m.missing.map((d, i) => <li key={i} className="miss">{d}</li>)}
                </ul>
              }
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
