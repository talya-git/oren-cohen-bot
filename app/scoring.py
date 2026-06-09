"""סיווג דטרמיניסטי של ליד על בסיס הפרמטרים שחולצו.

הלוגיקה כאן בקוד — לא ב-LLM — כדי שהסיווג יהיה יציב, שקוף, וניתן לכיול.
המשקלים והספים הם נקודת פתיחה; תקופת הדמו עם הסוכנים היא מה שיכייל אותם.
"""

from .schemas import ExtractedParams, LeadScore

# משקלים — סכומם 1.0
WEIGHTS = {
    "budget": 0.35,
    "timeline": 0.25,
    "financing": 0.20,
    "intent": 0.10,
    "engagement": 0.10,
}

# ספים לרמות הסיווג
HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.45


def _score_budget(budget_ils: int | None) -> float:
    """ספים מותאמים לשוק היוקרה בירושלים. כיילי לפי הנתונים שלכם."""
    if budget_ils is None:
        return 0.3  # לא ידוע — ניטרלי-נמוך
    if budget_ils >= 8_000_000:
        return 1.0
    if budget_ils >= 5_000_000:
        return 0.85
    if budget_ils >= 3_000_000:
        return 0.6
    if budget_ils >= 1_500_000:
        return 0.4
    return 0.2


def _score_timeline(timeline: str) -> float:
    return {
        "immediate": 1.0,
        "3_months": 0.8,
        "6_12_months": 0.5,
        "exploring": 0.2,
        "unknown": 0.3,
    }.get(timeline, 0.3)


def _score_financing(financing: str) -> float:
    return {
        "cash": 1.0,
        "mortgage_approved": 0.85,
        "mortgage_needed": 0.4,
        "unknown": 0.3,
    }.get(financing, 0.3)


def _score_intent(intent: str) -> float:
    return {
        "buy": 0.9,
        "invest": 0.9,
        "sell": 0.7,
        "browsing": 0.2,
        "unknown": 0.3,
    }.get(intent, 0.3)


def _score_engagement(engagement: str) -> float:
    return {"high": 1.0, "medium": 0.6, "low": 0.3}.get(engagement, 0.6)


def score_lead(params: ExtractedParams) -> LeadScore:
    breakdown = {
        "budget": _score_budget(params.budget_ils),
        "timeline": _score_timeline(params.timeline),
        "financing": _score_financing(params.financing),
        "intent": _score_intent(params.intent),
        "engagement": _score_engagement(params.engagement),
    }
    score = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)

    if score >= HIGH_THRESHOLD:
        level = "High"
    elif score >= MEDIUM_THRESHOLD:
        level = "Medium"
    else:
        level = "Low"

    return LeadScore(score=round(score, 3), level=level, breakdown=breakdown)
