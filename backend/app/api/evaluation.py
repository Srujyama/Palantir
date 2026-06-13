"""Evaluation endpoints.

Exposes the classifier scorecard (/eval/summary) and the named list of
misclassified patients (/eval/misses) over the live DB. The truth labels are
held-out fields on Patient rows — they ship with the corpus for exactly this
purpose and never drive runtime behavior.

Operational coordination tooling, NOT a clinical decision aid.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.evaluation import evaluate_corpus, misclassified


router = APIRouter(prefix="/eval", tags=["evaluation"])


class CategoryMetrics(BaseModel):
    category: str
    precision: float
    recall: float
    f1: float
    support: int


class ConfusionCell(BaseModel):
    truth: str
    predicted: str
    count: int


class OwnerRouting(BaseModel):
    n: int
    accuracy: float


class EvalSummary(BaseModel):
    n: int
    accuracy: float
    per_category: List[CategoryMetrics]
    confusion: List[ConfusionCell]
    owner_routing: OwnerRouting


class MissRow(BaseModel):
    patient_id: str
    miss_type: str  # "category" | "owner"
    truth: str
    predicted: str
    urgency: str
    template_name: Optional[str]


@router.get("/summary", response_model=EvalSummary)
def eval_summary(db: Session = Depends(get_db)) -> EvalSummary:
    """Classifier scorecard against held-out truth labels."""
    return EvalSummary(**evaluate_corpus(db))


@router.get("/misses", response_model=List[MissRow])
def eval_misses(db: Session = Depends(get_db)) -> List[MissRow]:
    """Misclassified patients, by name, for debugging honesty."""
    return [MissRow(**m) for m in misclassified(db)]
