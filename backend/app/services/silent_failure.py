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
from typing import List

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


# Words that, when within `_NEGATION_WINDOW` chars of a trigger, mean the
# trigger is historical / negated / already resolved and should NOT fire the
# protocol. This is a small, tuned set — clinical NLP literature calls it
# "context detection" (cf. NegEx/ConText).
_NEGATION_TOKENS = [
    "resolved", "denies", "no ", "not ", "improving", "improved",
    "ruled out", "history of", "h/o", "prior", "previous",
    "stable", "negative", "without", "afebrile",
    "admitted", "days ago", "weeks ago", "last admission",
    "post-op", "post op", "second admission", "third admission",
]
_NEGATION_WINDOW = 60

# A protocol-wide check: phrases that indicate the protocol's condition is
# already addressed/resolved/historical anywhere in the note, even if the
# trigger appears in the chief complaint with no nearby negation.
_PROTOCOL_RESOLUTION_PHRASES = {
    "dka": [r"DKA\s+resolved", r"anion\s+gap\s+closed", r"gap\s+closed", r"bicarbonate\s+(2[0-9]|[3-9]\d)"],
    "sepsis": [r"sepsis\s+resolved", r"afebrile\s+for"],
    "stroke": [r"stroke\s+resolved", r"deficits\s+resolved"],
    "cap": [r"pneumonia\s+(resolved|improving)"],
    "acs": [r"chest\s+pain\s+resolved", r"troponin\s+down-?trending"],
}
# Triggers that are short and ambiguous (e.g. "CVA" can mean costovertebral
# angle, not stroke). For these we require a stricter contextual confirmation.
_AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: dict[str, List[str]] = {
    r"\bCVA\b": ["stroke", "infarct", "tPA", "NIHSS", "hemiparesis", "aphasi", "facial droop"],
}


def _is_negated_or_historical(note: str, span: Span) -> bool:
    left = note[max(0, span.start - _NEGATION_WINDOW): span.start].lower()
    right = note[span.end: span.end + _NEGATION_WINDOW].lower()
    window = left + " " + right
    return any(tok in window for tok in _NEGATION_TOKENS)


def _ambiguous_trigger_passes(note: str, pattern: str, span: Span) -> bool:
    needs = _AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT.get(pattern)
    if not needs:
        return True
    return any(kw.lower() in note.lower() for kw in needs)


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


def silent_failures(note: str) -> List[SilentFailure]:
    """Return only the actionable misses across all triggered protocols."""
    out: List[SilentFailure] = []
    for pm in evaluate(note):
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
