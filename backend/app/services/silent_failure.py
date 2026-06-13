"""
Silent-failure detector.

Cross-references the extracted note signals against the care-pathway protocol
library. For each protocol whose triggers match the note, it checks every
expected action and reports those that are NOT documented as silent failures.

This is what differentiates the Radar from yet-another note summarizer:
"things that should have happened but didn't" is the operational signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.nlp.extractor import Span
from app.protocols.library import PROTOCOLS, Protocol, ExpectedAction


@dataclass
class SilentFailure:
    protocol_key: str
    protocol_name: str
    missing_action: str               # e.g. "Administer broad-spectrum antibiotics"
    severity: str                     # required | recommended
    citation: str
    trigger_evidence: Span            # what triggered the protocol
    owner: str
    urgency: str


@dataclass
class ProtocolMatch:
    protocol: Protocol
    triggered: bool
    trigger_evidence: List[Span] = field(default_factory=list)
    documented: List[ExpectedAction] = field(default_factory=list)
    missing: List[ExpectedAction] = field(default_factory=list)


# Trigger-context cues, two families (cf. NegEx/ConText), both clipped to
# the trigger's own sentence so a cue in a neighboring sentence never leaks:
#
#   * _NEGATION_TOKENS_LEFT — true negation cues. In English clinical prose
#     negation PRECEDES the negated concept ("no melena", "denies chest
#     pain"), so these are searched only in the LEFT context. Scanning the
#     right context caused two real bug classes: "Meets SIRS criteria. No
#     antibiotics given yet." suppressed the SIRS trigger, and "CXR no
#     infiltrate. Assessment: COPD exacerbation" suppressed the COPD trigger
#     (pre-clipping, the cue leaked across the sentence boundary).
#
#   * _HISTORICAL_TOKENS — historical / resolution cues. These legitimately
#     appear on either side of the trigger ("stroke 5 days ago",
#     "COPD exacerbation, resolved"), so both sides are searched, still
#     within the same sentence.
_NEGATION_TOKENS_LEFT = [
    "denies", "no ", "not ", "ruled out", "negative", "without", "free of",
]
_HISTORICAL_TOKENS = [
    "resolved", "improving", "improved", "history of", "h/o",
    "prior", "previous", "stable", "afebrile",
    "admitted", "days ago", "weeks ago", "last admission",
    "post-op", "post op", "second admission", "third admission",
]
_NEGATION_WINDOW = 60
# Sentence boundaries cap the cue window: a cue in the previous/next
# sentence must not negate a trigger in this one.
_SENTENCE_BOUNDARY = re.compile(r"[.!?;\n]")

# A protocol-wide check: phrases that indicate the protocol's condition is
# already addressed/resolved/historical anywhere in the note, even if the
# trigger appears in the chief complaint with no nearby negation.
_PROTOCOL_RESOLUTION_PHRASES = {
    "dka": [r"DKA\s+resolved", r"anion\s+gap\s+closed", r"gap\s+closed", r"bicarbonate\s+(2[0-9]|[3-9]\d)"],
    "sepsis": [r"sepsis\s+resolved", r"afebrile\s+for"],
    "stroke": [
        r"stroke\s+resolved", r"deficits\s+resolved",
        # Past the acute window: the tPA bundle no longer applies; the note
        # is in the rehab/disposition phase.
        r"(stroke|tPA|thrombolysis)\s+window\s+(expired|closed|passed)",
    ],
    "cap": [r"pneumonia\s+(resolved|improving)"],
    "acs": [
        r"chest\s+pain\s+resolved", r"troponin\s+down-?trending",
        # Rule-out language: serial negative troponins / explicit rule-out
        # means the ACS pathway is concluded, not incomplete.
        r"two\s+negative\s+troponins?", r"troponins?\s+x\s*2\s+negative",
        r"chest\s+pain.{0,40}ruled\s+out", r"non-?cardiac\s+chest\s+pain",
    ],
    "pe": [r"PE\s+resolved", r"clot\s+burden\s+(decreased|improving)"],
    "gi_bleed": [r"bleeding\s+(stopped|resolved)", r"hgb\s+(stable|recovered)"],
    "aki": [r"AKI\s+(resolved|improving)", r"creatinine\s+(returned|back\s+to\s+baseline)", r"renal\s+function\s+recovered"],
    "ciwa": [r"CIWA\s+(score|scores)\s+(<\s*8|low|0)", r"withdrawal\s+resolved"],
    "neutropenic_fever": [r"ANC\s+(recovered|>\s*500)", r"afebrile\s+for\s+\d+"],
    "hyperkalemia": [r"potassium\s+(normalized|corrected|back\s+to)", r"K\s+(3\.\d|4\.\d|5\.[0-2])"],
    # Note the optional comma: assessments are routinely written
    # "COPD exacerbation, resolved".
    "copd": [r"COPD\s+exacerbation,?\s+resolved", r"COPD\s+stable", r"back\s+to\s+baseline"],
}

# KDIGO-style severity gate for the AKI workup bundle: a mild creatinine
# bump ("developing AKI", Cr < 2.0 with preserved urine output) is managed
# by the nephrotoxin medication-review flag (interaction engine), not by
# demanding the full workup bundle. The bundle is owed once AKI is
# established/severe: Cr >= 2.0, a documented rise to >= 2.0, oliguria /
# anuria, or ATN sediment.
_AKI_SEVERITY_CONTEXT: List[str] = [
    r"(?:creatinine|\bCr\b)\s*[: ]?\s*(?:[2-9]|[1-9]\d)\.\d",
    r"\bto\s+(?:[2-9]|[1-9]\d)\.\d",
    r"\bUOP\s*<", r"oliguri", r"anuri", r"muddy\s+brown",
]

# Triggers that are short or non-specific on their own (e.g. "CVA" can mean
# costovertebral angle, not stroke; "AKI" language may describe a mild bump
# that does not yet owe the full workup bundle). For these we require a
# corroborating context pattern anywhere in the note.
_AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: dict[str, List[str]] = {
    r"\bCVA\b": ["stroke", "infarct", "tPA", "NIHSS", "hemiparesis", "aphasi", "facial droop"],
    r"\bAKI\b": _AKI_SEVERITY_CONTEXT,
    r"acute\s+kidney\s+injury": _AKI_SEVERITY_CONTEXT,
    r"creatinine\s+(rising|rose|increased|elevated)": _AKI_SEVERITY_CONTEXT,
}


def _is_negated_or_historical(note: str, span: Span) -> bool:
    left = note[max(0, span.start - _NEGATION_WINDOW): span.start].lower()
    left = _SENTENCE_BOUNDARY.split(left)[-1]    # same sentence only
    right = note[span.end: span.end + _NEGATION_WINDOW].lower()
    right = _SENTENCE_BOUNDARY.split(right)[0]   # same sentence only
    # Negation precedes its concept in English clinical prose: left only.
    if any(tok in left for tok in _NEGATION_TOKENS_LEFT):
        return True
    # Historical/resolution context can sit on either side of the trigger.
    return any(tok in left or tok in right for tok in _HISTORICAL_TOKENS)


def _ambiguous_trigger_passes(note: str, pattern: str, span: Span) -> bool:
    needs = _AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT.get(pattern)
    if not needs:
        return True
    return any(re.search(kw, note, flags=re.IGNORECASE) for kw in needs)


def _find_first(note: str, patterns: List[str]) -> Span | None:
    """Find the first trigger that is neither historical/negated nor an
    ambiguous abbreviation lacking corroborating context."""
    for pat in patterns:
        for m in re.finditer(pat, note, flags=re.IGNORECASE):
            span = Span(m.start(), m.end(), m.group(0))
            if _is_negated_or_historical(note, span):
                continue
            if not _ambiguous_trigger_passes(note, pat, span):
                continue
            return span
    return None


def _any_match(note: str, patterns: List[str]) -> bool:
    return any(re.search(p, note, flags=re.IGNORECASE) for p in patterns)


def _protocol_resolved(note: str, proto_key: str) -> bool:
    for pat in _PROTOCOL_RESOLUTION_PHRASES.get(proto_key, []):
        if re.search(pat, note, flags=re.IGNORECASE):
            return True
    return False


def evaluate(note: str) -> List[ProtocolMatch]:
    """Return per-protocol triggered/documented/missing breakdown for a note."""
    out: List[ProtocolMatch] = []
    for proto in PROTOCOLS:
        trig = _find_first(note, proto.triggers)
        if not trig or _protocol_resolved(note, proto.key):
            out.append(ProtocolMatch(protocol=proto, triggered=False))
            continue

        documented, missing = [], []
        for action in proto.expected_actions:
            if _any_match(note, action.documented_patterns):
                documented.append(action)
            else:
                missing.append(action)

        out.append(
            ProtocolMatch(
                protocol=proto,
                triggered=True,
                trigger_evidence=[trig],
                documented=documented,
                missing=missing,
            )
        )
    return out


def silent_failures(
    note: str, matches: Optional[List[ProtocolMatch]] = None
) -> List[SilentFailure]:
    """Return only the actionable misses across all triggered protocols.

    `matches` lets callers that already ran `evaluate(note)` (e.g. the
    bottleneck classifier) pass the result in instead of re-evaluating every
    protocol against the note. When omitted, behavior is identical to before:
    `evaluate(note)` is computed here.
    """
    out: List[SilentFailure] = []
    for pm in (matches if matches is not None else evaluate(note)):
        if not pm.triggered:
            continue
        for action in pm.missing:
            out.append(
                SilentFailure(
                    protocol_key=pm.protocol.key,
                    protocol_name=pm.protocol.name,
                    missing_action=action.label,
                    severity=action.severity,
                    citation=pm.protocol.citation,
                    trigger_evidence=pm.trigger_evidence[0] if pm.trigger_evidence else Span(0, 0, ""),
                    owner=pm.protocol.owner,
                    urgency=pm.protocol.urgency_if_incomplete,
                )
            )
    return out
