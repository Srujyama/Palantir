import type { LabTrend } from "../types/api";

const STROKE: Record<LabTrend["clinical"], string> = {
  worsening: "var(--signal-red)",
  improving: "var(--signal-green)",
  stable: "var(--fg-2)",
  unknown: "var(--fg-2)",
};

interface SparklineProps {
  points: (number | null)[];
  clinical: LabTrend["clinical"];
  width?: number;
  height?: number;
}

/**
 * Hand-rolled inline SVG sparkline. No chart lib, no deps.
 * Normalizes real (non-null) values to the [min,max] range, plots a polyline
 * that skips null gaps, and dots every real point. Stroke is colored by the
 * lab's clinical direction (worsening red / improving green / else neutral).
 */
export function Sparkline({ points, clinical, width = 120, height = 30 }: SparklineProps) {
  const stroke = STROKE[clinical] ?? "var(--fg-2)";
  const padX = 3;
  const padY = 4;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const reals = points.filter((p): p is number => p !== null && Number.isFinite(p));
  // Nothing to draw — render an empty baseline so layout stays stable.
  if (reals.length === 0) {
    return (
      <svg
        className="spark-svg"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="no trend data"
      >
        <line
          x1={padX}
          y1={height / 2}
          x2={width - padX}
          y2={height / 2}
          stroke="var(--border-strong)"
          strokeWidth={1}
        />
      </svg>
    );
  }

  let min = Math.min(...reals);
  let max = Math.max(...reals);
  if (min === max) {
    // Flat series — center it so the dot/line sits mid-band.
    min -= 1;
    max += 1;
  }
  const span = max - min;

  const n = points.length;
  const xAt = (i: number) =>
    n <= 1 ? padX + innerW / 2 : padX + (i / (n - 1)) * innerW;
  const yAt = (v: number) => padY + (1 - (v - min) / span) * innerH;

  // Build polyline segments, breaking the line wherever a null gap appears so
  // we never draw a phantom edge across missing data.
  const segments: string[] = [];
  let current: string[] = [];
  points.forEach((p, i) => {
    if (p === null || !Number.isFinite(p)) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      return;
    }
    current.push(`${xAt(i).toFixed(1)},${yAt(p).toFixed(1)}`);
  });
  if (current.length > 1) segments.push(current.join(" "));

  const dots = points
    .map((p, i) => (p !== null && Number.isFinite(p) ? { x: xAt(i), y: yAt(p), i } : null))
    .filter((d): d is { x: number; y: number; i: number } => d !== null);

  return (
    <svg
      className="spark-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`trend ${clinical}`}
    >
      {segments.map((pts, idx) => (
        <polyline
          key={idx}
          points={pts}
          fill="none"
          stroke={stroke}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
      {dots.map((d) => (
        <circle key={d.i} cx={d.x} cy={d.y} r={1.8} fill={stroke} />
      ))}
    </svg>
  );
}
