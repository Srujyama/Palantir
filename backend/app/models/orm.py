"""SQLAlchemy ORM models for the Bottleneck Radar.

Conceptually these are the Foundry ontology objects:

  Patient        - clinical subject and the note we read
  Triage         - the result of running the pipeline on a patient note
  Action         - an actionable task created from a bottleneck (assigned, owned)

Triage rows are regenerated from notes on every ingest, so they're effectively
materializations. Actions persist across ingests so the workflow state is real.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True)             # e.g. P-1042
    age = Column(Integer, nullable=False)
    sex = Column(String, nullable=False)
    chief_complaint = Column(String, nullable=False)
    note_text = Column(Text, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    template_name = Column(String, nullable=True)     # debug provenance
    truth_bottleneck = Column(String, nullable=True)  # for eval; not exposed in UI
    room = Column(String, nullable=True)              # e.g. "3E-12" floor-east bed 12

    triage = relationship("Triage", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="patient", cascade="all, delete-orphan")
    note_versions = relationship(
        "NoteVersion",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="NoteVersion.sequence",
    )


class NoteVersion(Base):
    """An earlier note for a patient — clinical history, not the current state.

    The current note always lives on Patient.note_text and is the *only* thing
    the classifier reads. NoteVersion rows hold prior snapshots so the trend
    engine can show trajectory (lactate clearing, creatinine worsening) without
    ever feeding history into the deterministic classification path.
    """

    __tablename__ = "note_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)        # 0 = oldest prior, ascending
    hours_ago = Column(Integer, nullable=False)       # offset from current note, as authored
    captured_at = Column(DateTime, nullable=False)    # arrival_time - hours_ago
    note_text = Column(Text, nullable=False)

    patient = relationship("Patient", back_populates="note_versions")


class Triage(Base):
    __tablename__ = "triage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, unique=True)
    primary_category = Column(String, nullable=False)
    primary_label = Column(String, nullable=False)
    primary_urgency = Column(String, nullable=False)        # red | amber | green
    primary_owner = Column(String, nullable=False)
    primary_action = Column(String, nullable=False)
    primary_rationale = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False)                  # full TriageResult.to_dict()
    extraction = Column(JSON, nullable=False)               # full ExtractionResult.to_dict()
    icd_candidates = Column(JSON, nullable=False)
    trends = Column(JSON, nullable=True)                    # longitudinal trajectory (narrative only)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    patient = relationship("Patient", back_populates="triage")


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    owner = Column(String, nullable=False)
    urgency = Column(String, nullable=False)
    status = Column(String, nullable=False, default="open")  # open | in_progress | resolved | escalated
    source_category = Column(String, nullable=False)         # which bottleneck created it
    sla_minutes = Column(Integer, nullable=True)             # policy window from app.services.sla
    due_at = Column(DateTime, nullable=True)                 # created_at + sla_minutes
    escalation_level = Column(Integer, nullable=False, default=0)  # bumped on each SLA breach
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    patient = relationship("Patient", back_populates="actions")
    events = relationship("ActionEvent", back_populates="action", cascade="all, delete-orphan", order_by="ActionEvent.created_at")


class ActionEvent(Base):
    """Audit-trail row for every state change on an Action.

    Real ops tools need an immutable log of who did what when. We record
    creation, status transitions, owner reassignments and free-text notes.
    """

    __tablename__ = "action_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)              # created | status_change | reassigned | note
    from_value = Column(String, nullable=True)
    to_value = Column(String, nullable=True)
    actor = Column(String, nullable=False, default="charge-rn")  # demo synthetic actor
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    action = relationship("Action", back_populates="events")
