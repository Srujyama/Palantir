"""
ICD-10 candidate matcher.

Given a free-text patient note, return the top-k most relevant codes from the
curated ICD-10 reference using TF-IDF + cosine similarity. This is a real,
auditable retrieval approach: every match has a similarity score and a code
description the reviewer can sanity-check.

For the demo this beats a black-box embedding model: clinicians can see why
each code surfaced and the build doesn't ship a 400 MB transformer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


REF_PATH = Path(__file__).parent.parent / "data" / "icd10_reference.json"

# Clinical abbreviations expanded before vectorizing the query. Notes say
# "AKI"; ICD-10 descriptions say "acute kidney failure/injury" — without
# expansion the TF-IDF vocabularies never meet. Expansions are APPENDED to
# the note text (the original is kept verbatim), so character offsets and any
# behavior outside this matcher are unaffected. All-uppercase keys match
# case-sensitively so e.g. "AF" never fires on the word "af(ter)" fragments
# or lowercase prose.
ABBREVIATION_EXPANSIONS: Dict[str, str] = {
    "AKI": "acute kidney injury acute kidney failure",
    "NSTEMI": "non-ST elevation myocardial infarction",
    "STEMI": "ST elevation myocardial infarction",
    "MI": "myocardial infarction",
    "GIB": "gastrointestinal bleeding hemorrhage",
    "CHF": "congestive heart failure",
    "COPD": "chronic obstructive pulmonary disease",
    "DKA": "diabetic ketoacidosis diabetes mellitus",
    "PE": "pulmonary embolism",
    "DVT": "deep vein thrombosis",
    "UTI": "urinary tract infection",
    "CVA": "cerebrovascular accident stroke cerebral infarction",
    "TIA": "transient ischemic attack",
    "ESRD": "end stage renal disease",
    "CKD": "chronic kidney disease",
    "AF": "atrial fibrillation",
    "A-fib": "atrial fibrillation",
    "AFib": "atrial fibrillation",
    "HTN": "hypertension",
    "T1DM": "type 1 diabetes mellitus",
    "T2DM": "type 2 diabetes mellitus",
    "SOB": "shortness of breath dyspnea",
    "AMS": "altered mental status",
    "abd": "abdominal",
    "GERD": "gastroesophageal reflux disease",
}


def expand_abbreviations(note: str) -> str:
    """Append full-phrase expansions for clinical abbreviations in `note`.

    The original text is preserved unchanged at the start of the returned
    string; matched expansions are appended at the end. All-uppercase
    abbreviations are matched case-sensitively, mixed/lowercase ones
    case-insensitively.
    """
    expansions: List[str] = []
    for abbrev, full in ABBREVIATION_EXPANSIONS.items():
        flags = 0 if abbrev.isupper() else re.IGNORECASE
        if re.search(rf"\b{re.escape(abbrev)}\b", note, flags):
            expansions.append(full)
    if not expansions:
        return note
    return note + " " + " ".join(expansions)


@dataclass
class ICDMatch:
    code: str
    description: str
    score: float
    category: str


class ICD10Matcher:
    def __init__(self) -> None:
        self._codes: List[dict] = json.loads(REF_PATH.read_text())
        descriptions = [c["description"] for c in self._codes]
        # Bigrams help: "heart failure", "kidney injury", "atrial fibrillation"
        self._vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            stop_words="english",
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(descriptions)

    def match(self, note: str, k: int = 5, min_score: float = 0.05) -> List[ICDMatch]:
        if not note.strip():
            return []
        q = self._vectorizer.transform([expand_abbreviations(note)])
        sims = cosine_similarity(q, self._matrix)[0]
        order = np.argsort(-sims)
        out: List[ICDMatch] = []
        for idx in order[:k]:
            score = float(sims[idx])
            if score < min_score:
                break
            entry = self._codes[idx]
            out.append(
                ICDMatch(
                    code=entry["code"],
                    description=entry["description"],
                    score=round(score, 3),
                    category=entry["category"],
                )
            )
        return out


_singleton: ICD10Matcher | None = None


def matcher() -> ICD10Matcher:
    global _singleton
    if _singleton is None:
        _singleton = ICD10Matcher()
    return _singleton
