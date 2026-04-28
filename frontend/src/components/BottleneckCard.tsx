import type { Bottleneck } from "../types/api";
import { ownerLabel } from "../lib/format";
import { UrgencyPill } from "./UrgencyPill";

export function BottleneckCard({ b, isPrimary }: { b: Bottleneck; isPrimary?: boolean }) {
  return (
    <div className="bottleneck-card">
      <div className="row">
        <UrgencyPill urgency={b.urgency} />
        <span className="label">{b.label}</span>
        {isPrimary && <span className="tag" style={{ color: "var(--signal-blue)" }}>PRIMARY</span>}
      </div>
      <div className="meta">
        <span><span className="k">OWNER</span>&nbsp;{ownerLabel(b.owner)}</span>
        <span><span className="k">CATEGORY</span>&nbsp;{b.category}</span>
      </div>
      <div className="action">
        <span className="k">Recommended next action</span>
        {b.recommended_action}
      </div>
      <div className="rationale">{b.rationale}</div>
      {b.citation && (
        <div className="citation">SOURCE&nbsp;·&nbsp;{b.citation}</div>
      )}
    </div>
  );
}
