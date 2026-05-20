"""Pydantic schemas for the public API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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


class ActionUpdate(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = None


class StatsResponse(BaseModel):
    total_patients: int
    by_urgency: Dict[str, int]
    by_category: Dict[str, int]
    by_owner: Dict[str, int]
    open_actions: int
    silent_failures: int
    median_arrival_age_hours: float
