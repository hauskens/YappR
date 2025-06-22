from math import exp
from datetime import datetime, timezone
from app.models.db import ContentQueue
ONE_HOUR       = 3600              # seconds
TAU_FRESH      = 12 * 3600          # freshness half-life
TAU_DURATION   = 120               # duration half-life (2-min clips lose ~63 %)

def freshness(age_seconds: float) -> float:
    """Penalise backlog, but never boost brand-new submissions."""
    if age_seconds <= ONE_HOUR:
        return 0.95
    # return 1 / (1 + (age_seconds - ONE_HOUR) / TAU_FRESH)
    return exp(-(age_seconds - ONE_HOUR) / TAU_FRESH)

def duration_weight(seconds: float) -> float:
    """Optional penalty that down-weights long clips."""
    return exp(-seconds / TAU_DURATION)

def clip_score(
        item: "ContentQueue",
        now: datetime | None = None,
        prefer_shorter: bool = False
    ) -> float:
    """Composite score = popularity × freshness × (optionally) duration."""
    now = now or datetime.now(timezone.utc)

    # how long since the **earliest** submission of this deduped clip
    age_sec = (now - min(item.submissions,
                         key=lambda s: s.submitted_at).submitted_at.replace(tzinfo=timezone.utc)).total_seconds()

    score = item.total_weight * freshness(age_sec)

    if prefer_shorter:
        score *= duration_weight(item.content.duration or 0)

    return score