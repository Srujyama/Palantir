import type { CensusPointOut } from "../types/api";

interface CensusTrendProps {
  points: CensusPointOut[];
  /** Full card width is the default; the card sets the box. */
  height?: number;
}

function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Hand-rolled multi-series census sparkline. No chart lib, no deps.
 *
 * Three lines share one count axis: census (neutral, the dominant line) plus
 * red/amber overlays in their signal colors so you can see the floor's acuity
 * mix move over time. The SVG fills its container width (viewBox + 100% width)
 * and a fixed pixel height. Axis labels are mono 10px: first/last captured_at
 * on x, min/max count on y.
 *
 * Points arrive oldest-first (per the contract). Fewer than two points cannot
 * make a line, so we render an empty-state instead.
 */
export function CensusTrend({ points, height = 160 }: CensusTrendProps) {
  if (points.length < 2) {
    return (
      <div className="empty-state">
        No census history yet — run a live tick to start the trend.
      </div>
    );
  }

  // viewBox coordinate space; the SVG scales to the card width via width="100%".
  const VBW = 1000;
  const VBH = height;
  const padL = 34; // room for y-axis count labels
  const padR = 8;
  const padT = 10;
  const padB = 20; // room for x-axis time labels
  const innerW = VBW - padL - padR;
  const innerH = VBH - padT - padB;

  const n = points.length;
  // Shared y-scale across all three series so they're directly comparable.
  const maxVal = Math.max(
    1,
    ...points.map((p) => Math.max(p.census, p.red, p.amber)),
  );

  const xAt = (i: number) => padL + (i / (n - 1)) * innerW;
  const yAt = (v: number) => padT + (1 - v / maxVal) * innerH;

  const lineFor = (key: "census" | "red" | "amber") =>
    points.map((p, i) => `${xAt(i).toFixed(1)},${yAt(p[key]).toFixed(1)}`).join(" ");

  // Horizontal gridlines at 0, mid, max — keeps the band readable without a lib.
  const gridVals = [0, Math.round(maxVal / 2), maxVal].filter(
    (v, i, a) => a.indexOf(v) === i,
  );

  const first = points[0];
  const last = points[n - 1];

  return (
    <div className="census-trend">
      <svg
        className="census-trend-svg"
        viewBox={`0 0 ${VBW} ${VBH}`}
        width="100%"
        height={height}
        preserveAspectRatio="none"
        role="img"
        aria-label="census over time"
      >
        {/* gridlines + y-axis count labels */}
        {gridVals.map((v) => (
          <g key={v}>
            <line
              x1={padL}
              y1={yAt(v)}
              x2={VBW - padR}
              y2={yAt(v)}
              stroke="var(--border)"
              strokeWidth={1}
            />
            <text
              x={padL - 6}
              y={yAt(v)}
              className="census-axis"
              textAnchor="end"
              dominantBaseline="middle"
            >
              {v}
            </text>
          </g>
        ))}

        {/* amber + red overlays first (thin), census on top (dominant) */}
        <polyline
          points={lineFor("amber")}
          fill="none"
          stroke="var(--signal-amber)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <polyline
          points={lineFor("red")}
          fill="none"
          stroke="var(--signal-red)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        <polyline
          points={lineFor("census")}
          fill="none"
          stroke="var(--fg-1)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />

        {/* x-axis time labels: first + last captured_at */}
        <text x={padL} y={VBH - 4} className="census-axis" textAnchor="start">
          {hhmm(first.captured_at)}
        </text>
        <text x={VBW - padR} y={VBH - 4} className="census-axis" textAnchor="end">
          {hhmm(last.captured_at)}
        </text>
      </svg>

      <div className="census-legend">
        <span className="census-legend-item">
          <span className="census-swatch census-swatch-census" /> Census
        </span>
        <span className="census-legend-item">
          <span className="census-swatch census-swatch-red" /> Red
        </span>
        <span className="census-legend-item">
          <span className="census-swatch census-swatch-amber" /> Amber
        </span>
        <span className="census-legend-count mono">{n} pts</span>
      </div>
    </div>
  );
}
