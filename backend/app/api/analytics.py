"""Aggregate analytics for the operations dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient, Triage
from app.models.schemas import AnalyticsResponse, ProtocolGapBreakdown


router = APIRouter(prefix="/analytics", tags=["analytics"])


AGE_BUCKETS = [
    ("0-6h", 0, 6),
    ("6-12h", 6, 12),
    ("12-24h", 12, 24),
    ("24-48h", 24, 48),
    ("48-72h", 48, 72),
    (">72h", 72, 9_999),
]


@router.get("", response_model=AnalyticsResponse)
def analytics(db: Session = Depends(get_db)):
    patients = db.query(Patient).all()
    triage_rows = db.query(Triage).all()
    actions = db.query(Action).all()

    now = datetime.utcnow()

    # Urgency / category / owner
    by_urgency = Counter(t.primary_urgency for t in triage_rows)
    by_category = Counter(t.primary_label for t in triage_rows)
    by_owner = Counter(t.primary_owner or "—" for t in triage_rows)

    # Per-protocol breakdown: total triggered + total gaps + which actions miss most
    triggered: Counter[str] = Counter()
    gaps_count: Counter[str] = Counter()
    proto_names: Dict[str, str] = {}
    per_proto_actions: Dict[str, Counter] = defaultdict(Counter)

    for t in triage_rows:
        for pm in t.payload.get("protocol_matches", []):
            if not pm.get("triggered"):
                continue
            key = pm["protocol_key"]
            proto_names[key] = pm["protocol_name"]
            triggered[key] += 1
            for missing_action in pm.get("missing", []):
                per_proto_actions[key][missing_action] += 1
                gaps_count[key] += 1

    by_protocol: List[ProtocolGapBreakdown] = []
    for key in sorted(proto_names.keys(), key=lambda k: -gaps_count[k]):
        by_protocol.append(
            ProtocolGapBreakdown(
                protocol_key=key,
                protocol_name=proto_names[key],
                total_triggered=triggered[key],
                total_gaps=gaps_count[key],
                missing_by_action=dict(per_proto_actions[key]),
            )
        )

    # Arrival age histogram
    age_buckets: Dict[str, int] = {b[0]: 0 for b in AGE_BUCKETS}
    for p in patients:
        hours = (now - p.arrival_time).total_seconds() / 3600
        for label, lo, hi in AGE_BUCKETS:
            if lo <= hours < hi:
                age_buckets[label] += 1
                break

    action_status = Counter(a.status for a in actions)
    actions_per_owner = Counter(a.owner for a in actions if a.status in ("open", "in_progress"))

    # Silent failures by protocol
    sf_by_proto: Counter[str] = Counter()
    for t in triage_rows:
        for sf in t.payload.get("silent_failures", []):
            sf_by_proto[sf["protocol_name"]] += 1

    return AnalyticsResponse(
        total_patients=len(patients),
        by_urgency=dict(by_urgency),
        by_category=dict(by_category),
        by_owner=dict(by_owner),
        by_protocol=by_protocol,
        arrival_age_buckets=age_buckets,
        action_status=dict(action_status),
        actions_per_owner=dict(actions_per_owner),
        silent_failures_by_protocol=dict(sf_by_proto),
    )
