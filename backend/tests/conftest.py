"""Shared test fixtures.

`build_test_client` is the factory every API test file should use: it builds
an isolated in-memory SQLite DB, overrides the FastAPI dependency, seeds the
patients you hand it through the real pipeline, and returns both the client
and a session factory for direct DB assertions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.database import Base, get_db
from app.models.orm import Patient
from app.services.pipeline import run as run_pipeline


def build_test_client(
    seed_patients: Optional[List[Dict]] = None,
) -> Tuple[TestClient, sessionmaker]:
    """Build an isolated TestClient over a fresh in-memory DB.

    seed_patients: list of dicts with Patient column overrides. Only
    `id` and `note_text` are required; everything else gets a sane default.
    Each seeded patient is run through the real triage pipeline.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        try:
            db = TestingSession()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    if seed_patients:
        db = TestingSession()
        try:
            for i, spec in enumerate(seed_patients):
                defaults = dict(
                    age=60,
                    sex="F",
                    chief_complaint="Test complaint",
                    arrival_time=datetime.utcnow() - timedelta(hours=6),
                    template_name="test",
                    truth_bottleneck=None,
                    room=f"3E-{i + 1:02d}",
                )
                defaults.update(spec)
                patient = Patient(**defaults)
                db.add(patient)
                db.flush()
                run_pipeline(db, patient)
            db.commit()
        finally:
            db.close()

    return TestClient(app), TestingSession


def teardown_test_client() -> None:
    app.dependency_overrides.clear()
