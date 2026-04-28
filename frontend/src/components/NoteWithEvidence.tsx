import type { Span } from "../types/api";

interface Props {
  text: string;
  spans: { span: Span; level?: "red" | "amber" }[];
}

/**
 * Render a clinical note with non-overlapping evidence spans highlighted.
 *
 * Spans may overlap. We resolve by sorting and merging onto the first start.
 * Highlighting is informational only — the structured signals on the side
 * are the canonical record.
 */
export function NoteWithEvidence({ text, spans }: Props) {
  if (!spans.length) {
    return <pre className="note-text">{text}</pre>;
  }

  // Deduplicate by (start, end) and sort
  const sorted = [...spans]
    .filter((s) => s.span.end > s.span.start)
    .sort((a, b) => a.span.start - b.span.start);

  // Merge overlaps, keep the highest level (red > amber)
  const merged: { start: number; end: number; level: "red" | "amber" }[] = [];
  for (const s of sorted) {
    const level = s.level ?? "amber";
    if (merged.length === 0 || s.span.start >= merged[merged.length - 1].end) {
      merged.push({ start: s.span.start, end: s.span.end, level });
    } else {
      const top = merged[merged.length - 1];
      top.end = Math.max(top.end, s.span.end);
      if (level === "red") top.level = "red";
    }
  }

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  merged.forEach((m, i) => {
    if (m.start > cursor) {
      parts.push(<span key={`t-${i}`}>{text.slice(cursor, m.start)}</span>);
    }
    parts.push(
      <mark key={`e-${i}`} className={`ev ${m.level === "red" ? "red" : ""}`}>
        {text.slice(m.start, m.end)}
      </mark>,
    );
    cursor = m.end;
  });
  if (cursor < text.length) {
    parts.push(<span key="rest">{text.slice(cursor)}</span>);
  }
  return <pre className="note-text">{parts}</pre>;
}
