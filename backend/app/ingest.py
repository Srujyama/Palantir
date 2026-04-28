"""Build the SQLite DB from notional patient notes and run the pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.db.database import Base, SessionLocal, engine
from app.models.orm import Patient, Triage  # noqa: F401  (registers tables)
from app.services.pipeline import run as run_pipeline


NOTES_PATH = Path(__file__).parent / "data" / "patient_notes.json"


def main() -> None:
    print("Recreating schema…")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    notes = json.loads(NOTES_PATH.read_text())
    db = SessionLocal()
    try:
        for n in notes:
            p = Patient(
                id=n["patient_id"],
                age=n["age"],
                sex=n["sex"],
                chief_complaint=n["chief_complaint"],
                note_text=n["note_text"],
                arrival_time=datetime.fromisoformat(n["arrival_time"]),
                template_name=n["template_name"],
                truth_bottleneck=n["truth_bottleneck"],
            )
            db.add(p)
            db.flush()
            run_pipeline(db, p)
        db.commit()
        print(f"Ingested {len(notes)} patients and computed triage.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
