"""Offline rule-tuning harness for the Bottleneck Radar classifier.

Runs the pure pipeline (extract() + classify(), no DB, no API) over the
shipped labeled corpus (app/data/patient_notes.json) and reports:

  * corpus accuracy (primary.category vs truth_bottleneck)
  * owner-routing accuracy (primary.owner vs expected_owner)
  * a sparse confusion matrix (truth -> predicted)
  * per-template miss clusters, with predicted-vs-truth and the classifier
    rationale for a few examples per template

This is the tool used to tune rules: fix one miss cluster, re-run, keep the
change only if corpus accuracy improves and the unit suite stays green.

Usage:
    .venv/bin/python tools/eval_harness.py            # summary + miss clusters
    .venv/bin/python tools/eval_harness.py --examples 5   # more rationale examples
    .venv/bin/python tools/eval_harness.py --template copd_no_steroids  # one cluster
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.nlp.extractor import extract  # noqa: E402
from app.services.bottleneck import classify  # noqa: E402

NOTES_PATH = BACKEND_ROOT / "app" / "data" / "patient_notes.json"


def run_corpus(rows: List[Dict]) -> Dict:
    """Classify every labeled row; return metrics + per-row results."""
    labeled = [r for r in rows if r.get("truth_bottleneck")]
    results = []
    for row in labeled:
        note = row["note_text"]
        triage = classify(note, extract(note))
        results.append(
            {
                "patient_id": row["patient_id"],
                "template_name": row.get("template_name", "?"),
                "truth": row["truth_bottleneck"],
                "predicted": triage.primary.category,
                "truth_owner": row.get("expected_owner", ""),
                "predicted_owner": triage.primary.owner,
                "rationale": triage.primary.rationale,
                "urgency": triage.primary.urgency,
            }
        )

    n = len(results)
    correct = sum(1 for r in results if r["truth"] == r["predicted"])
    owner_correct = sum(1 for r in results if r["truth_owner"] == r["predicted_owner"])
    confusion: Counter = Counter(
        (r["truth"], r["predicted"]) for r in results if r["truth"] != r["predicted"]
    )
    misses_by_template: Dict[str, List[Dict]] = defaultdict(list)
    for r in results:
        if r["truth"] != r["predicted"]:
            misses_by_template[r["template_name"]].append(r)

    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n if n else 0.0,
        "owner_correct": owner_correct,
        "owner_accuracy": owner_correct / n if n else 0.0,
        "confusion": confusion,
        "misses_by_template": dict(misses_by_template),
        "results": results,
    }


def print_report(metrics: Dict, examples_per_template: int, only_template: str | None) -> None:
    print(f"corpus accuracy: {metrics['accuracy']:.4f} "
          f"({metrics['correct']}/{metrics['n']})")
    print(f"owner accuracy:  {metrics['owner_accuracy']:.4f} "
          f"({metrics['owner_correct']}/{metrics['n']})")

    print("\nconfusion (truth -> predicted, misses only):")
    for (truth, pred), count in sorted(
        metrics["confusion"].items(), key=lambda kv: -kv[1]
    ):
        print(f"  {truth:18s} -> {pred:18s} {count}")

    print("\nmisses by template:")
    clusters = sorted(
        metrics["misses_by_template"].items(), key=lambda kv: (-len(kv[1]), kv[0])
    )
    for template, misses in clusters:
        if only_template and template != only_template:
            continue
        first = misses[0]
        print(f"\n  {template}  ({len(misses)} misses)  "
              f"truth={first['truth']}  predicted={first['predicted']}")
        for m in misses[:examples_per_template]:
            print(f"    {m['patient_id']}: pred={m['predicted']}"
                  f" (owner={m['predicted_owner']}, urgency={m['urgency']})"
                  f" truth={m['truth']} (owner={m['truth_owner']})")
            print(f"      rationale: {m['rationale'][:220]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=int, default=3,
                        help="rationale examples to print per miss template")
    parser.add_argument("--template", default=None,
                        help="only print misses for this template_name")
    args = parser.parse_args()

    rows = json.loads(NOTES_PATH.read_text())
    metrics = run_corpus(rows)
    print_report(metrics, args.examples, args.template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
