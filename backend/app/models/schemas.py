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
    note_text: str
    primary: BottleneckPayload
    secondary: List[BottleneckPayload]
    silent_failures: List[SilentFailurePayload]
    protocol_matches: List[ProtocolMatchPayload]
    icd_candidates: List[ICDCandidate]
    extraction: Dict[str, Any]
    actions: List[ActionResponse]


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
