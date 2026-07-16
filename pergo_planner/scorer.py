from __future__ import annotations

from .optimizer import Candidate


def evaluate(candidate: Candidate) -> float:
    """Calculate score for a candidate."""
    raise NotImplementedError
