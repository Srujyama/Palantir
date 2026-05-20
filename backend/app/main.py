"""FastAPI app entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.analytics import router as analytics_router
from app.api.floor import router as floor_router
from app.api.handoff import router as handoff_router
from app.api.patients import router as patients_router
from app.api.stats import router as stats_router
from app.db.database import Base, engine


app = FastAPI(
    title="Clinical Bottleneck Radar API",
    version="0.1.0",
    description=(
        "Operational triage API for hospital throughput. Reads patient notes, "
        "extracts clinical signals, classifies the bottleneck blocking each "
        "patient, and exposes the queue + actions to the floor."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Make sure tables exist (no-op if they do).
Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


app.include_router(patients_router)
app.include_router(actions_router)
app.include_router(stats_router)
app.include_router(floor_router)
app.include_router(analytics_router)
app.include_router(handoff_router)
