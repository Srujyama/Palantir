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
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


REF_PATH = Path(__file__).parent.parent / "data" / "icd10_reference.json"


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
        q = self._vectorizer.transform([note])
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
