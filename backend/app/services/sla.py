"""
SLA policy engine for action lifecycle management.

This module is the single source of truth for "how long does the floor have
to act on this?". It is an explicit, ops-owned policy table — NOT a model and
NOT a clinical decision aid. In a Foundry deployment this table would live as
a versioned ontology object set with operational sign-off, so charge nurses
and throughput leads can tune it without touching code.

Policy table (minutes to act, keyed by (source_category, urgency); "*" is a
category-wide default):

    (source_category, urgency)      sla_minutes   derivation
    ---------------------------     -----------   ----------------------------------------
    missing_soc, red                60            1h bundles: sepsis hour-1, stroke,
                                                  neutropenic fever, hyperkalemia
                                                  (time_window_hours=1 in protocols/library)
    missing_soc, amber              240           4-6h bundles: COPD (4h), CAP (6h);
                                                  240 is the conservative bound
    med_risk, red                   60            active patient-safety exposure
    med_risk, amber                 120           safety review within a nursing shift block
    awaiting_consult, *             240           page + 30-min escalation ladder, x2 retries
    awaiting_imaging, *             180           radiology expedite window
    readmit_risk, *                 720           transitional-care setup, half a day
    dispo_delay, *                  1440          placement / auth work, one business day
    (anything else)                 480           default: one 8h shift

Every breach is written to the ActionEvent audit log (event_type="sla_breach")
so the escalation is traceable — deterministic rules, no black box.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from app.models.orm import Action


# (source_category, urgency) -> minutes. "*" matches any urgency for that
# category; exact (category, urgency) entries win over wildcards.
SLA_POLICIES: Dict[Tuple[str, str], int] = {
    ("missing_soc", "red"): 60,
    ("missing_soc", "amber"): 240,
    ("med_risk", "red"): 60,
    ("med_risk", "amber"): 120,
    ("awaiting_consult", "*"): 240,
    ("awaiting_imaging", "*"): 180,
    ("readmit_risk", "*"): 720,
    ("dispo_delay", "*"): 1440,
}

# Fallback when neither an exact nor a wildcard policy exists: one 8h shift.
DEFAULT_SLA_MINUTES = 480

# Statuses that still count as "work outstanding" for breach detection.
ACTIVE_STATUSES = frozenset({"open", "in_progress"})


def sla_minutes_for(source_category: str, urgency: str) -> int:
    """Resolve the SLA window in minutes for an action.

    Lookup order: exact (category, urgency) -> (category, "*") -> default.
    """
    exact = SLA_POLICIES.get((source_category, urgency))
    if exact is not None:
        return exact
    wildcard = SLA_POLICIES.get((source_category, "*"))
    if wildcard is not None:
        return wildcard
    return DEFAULT_SLA_MINUTES


def compute_due_at(created_at: datetime, source_category: str, urgency: str) -> datetime:
    """Deadline for an action created at `created_at` under the policy table."""
    return created_at + timedelta(minutes=sla_minutes_for(source_category, urgency))


def is_overdue(action: Action, now: Optional[datetime] = None) -> bool:
    """True when an unresolved action is past its deadline.

    Resolved actions are never overdue (the work is done); escalated actions
    stay flagged so breached items remain pinned in the queue. Actions with no
    due_at (legacy rows) cannot be overdue.
    """
    if action.due_at is None or action.status == "resolved":
        return False
    now = now or datetime.utcnow()
    return now > action.due_at


def minutes_remaining(action: Action, now: Optional[datetime] = None) -> Optional[int]:
    """Whole minutes until the deadline (negative when past it).

    Returns None when the action has no due_at.
    """
    if action.due_at is None:
        return None
    now = now or datetime.utcnow()
    return int((action.due_at - now).total_seconds() // 60)
