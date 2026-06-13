"""Pydantic schemas for the public API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


VALID_OWNERS = {"physician", "nurse", "pharmacist", "case_manager", "social_worker"}
VALID_URGENCIES = {"red", "amber", "green"}


class PatientSummary(BaseModel):
    id: str
    age: int
    sex: str
    chief_complaint: str
    arrival_time: datetime
    room: Optional[str] = None
    primary_category: str
    primary_label: str
    primary_urgency: str
    primary_owner: str
    primary_action: str
    open_actions: int
    overdue_actions: int = 0
    silent_failure_count: int


class Span(BaseModel):
    start: int
    end: int
    text: str


class BottleneckPayload(BaseModel):
    category: str
    label: str
    urgency: str
    owner: str
    recommended_action: str
    rationale: str
    evidence: List[Span] = Field(default_factory=list)
    citation: Optional[str] = None


class SilentFailurePayload(BaseModel):
    protocol_key: str
    protocol_name: str
    missing_action: str
    severity: str
    citation: str
    trigger_evidence: Span
    owner: str
    urgency: str


class ProtocolMatchPayload(BaseModel):
    protocol_key: str
    protocol_name: str
    triggered: bool
    documented: List[str]
    missing: List[str]
    trigger_evidence: List[Span]
    citation: str
    time_window_hours: int


class ICDCandidate(BaseModel):
    code: str
    description: str
    score: float
    category: str


class ActionResponse(BaseModel):
    id: int
    patient_id: str
    title: str
    description: str
    owner: str
    urgency: str
    status: str
    source_category: str
    sla_minutes: Optional[int] = None
    due_at: Optional[datetime] = None
    escalation_level: int = 0
    overdue: bool = False
    minutes_remaining: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class PatientDetail(BaseModel):
    id: str
    age: int
    sex: str
    chief_complaint: str
    arrival_time: datetime
    room: Optional[str] = None
    note_text: str
    primary: BottleneckPayload
    secondary: List[BottleneckPayload]
    silent_failures: List[SilentFailurePayload]
    protocol_matches: List[ProtocolMatchPayload]
    icd_candidates: List[ICDCandidate]
    extraction: Dict[str, Any]
    actions: List[ActionResponse]


class ActionEventResponse(BaseModel):
    id: int
    action_id: int
    event_type: str
    from_value: Optional[str] = None
    to_value: Optional[str] = None
    actor: str
    note: Optional[str] = None
    created_at: datetime


class FloorBed(BaseModel):
    """One bed on the floor map."""

    room: str
    wing: str
    bed_number: int
    patient_id: Optional[str] = None
    urgency: Optional[str] = None
    primary_category: Optional[str] = None
    primary_owner: Optional[str] = None
    chief_complaint: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    open_actions: int = 0


class FloorMap(BaseModel):
    wings: List[str]
    beds_per_wing: int
    beds: List[FloorBed]


class TimelineEvent(BaseModel):
    """One row on the patient timeline."""

    timestamp: datetime
    kind: str            # arrival | triage | gap_detected | action_created | action_state | note
    title: str
    detail: Optional[str] = None
    urgency: Optional[str] = None
    actor: Optional[str] = None


class PatientTimeline(BaseModel):
    patient_id: str
    events: List[TimelineEvent]


class ProtocolGapBreakdown(BaseModel):
    protocol_key: str
    protocol_name: str
    total_triggered: int
    total_gaps: int
    missing_by_action: Dict[str, int]


class AnalyticsResponse(BaseModel):
    """Aggregate operational metrics for the analytics page."""

    total_patients: int
    by_urgency: Dict[str, int]
    by_category: Dict[str, int]
    by_owner: Dict[str, int]
    by_protocol: List[ProtocolGapBreakdown]
    arrival_age_buckets: Dict[str, int]       # "0-6h", "6-12h" ...
    action_status: Dict[str, int]
    actions_per_owner: Dict[str, int]
    silent_failures_by_protocol: Dict[str, int]


class HandoffSection(BaseModel):
    title: str
    patient_id: Optional[str] = None
    room: Optional[str] = None
    urgency: Optional[str] = None
    bullets: List[str]


class HandoffReport(BaseModel):
    generated_at: datetime
    shift_label: str
    floor: str
    summary: Dict[str, int]
    critical: List[HandoffSection]
    open_protocol_gaps: List[HandoffSection]
    awaiting_dispo: List[HandoffSection]
    open_actions_by_owner: Dict[str, List[HandoffSection]]


class WhyStuckResponse(BaseModel):
    patient_id: str
    summary: str
    bullet_points: List[str]
    primary: BottleneckPayload
    contributing: List[BottleneckPayload]
    silent_failures: List[SilentFailurePayload]


class ActionCreate(BaseModel):
    title: str
    description: str
    owner: str
    urgency: str
    source_category: str
    actor: str = "charge-rn"

    @field_validator("owner")
    @classmethod
    def _owner_valid(cls, v: str) -> str:
        if v not in VALID_OWNERS:
            raise ValueError(f"owner must be one of {sorted(VALID_OWNERS)}")
        return v

    @field_validator("urgency")
    @classmethod
    def _urgency_valid(cls, v: str) -> str:
        if v not in VALID_URGENCIES:
            raise ValueError(f"urgency must be one of {sorted(VALID_URGENCIES)}")
        return v


class ActionUpdate(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = None
    actor: str = "charge-rn"

    @field_validator("owner")
    @classmethod
    def _owner_valid(cls, v):
        # A reassignment must target a real role; reject empty strings too.
        # (status transitions are validated against the state machine below.)
        if v is not None and v not in VALID_OWNERS:
            raise ValueError(f"owner must be one of {sorted(VALID_OWNERS)}")
        return v


class ActionNoteCreate(BaseModel):
    note: str
    actor: str = "charge-rn"


class SweepResponse(BaseModel):
    """Result of one SLA sweep pass."""

    checked: int
    breached: int
    escalated_ids: List[int]


class BulkUpdateResponse(BaseModel):
    """Bulk PATCH report: full rows that changed, plus ids we could not act on.

    `missing` lists ids that don't exist; `skipped` lists ids whose requested
    status change violated the action state machine (with the reason).
    """

    updated: List[ActionResponse]
    missing: List[int] = Field(default_factory=list)
    skipped: List[Dict[str, Any]] = Field(default_factory=list)


class StatsResponse(BaseModel):
    total_patients: int
    by_urgency: Dict[str, int]
    by_category: Dict[str, int]
    by_owner: Dict[str, int]
    open_actions: int
    silent_failures: int
    median_arrival_age_hours: float
