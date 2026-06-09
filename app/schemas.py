"""סכמות Pydantic — מבנה הנתונים שעובר בין הבוט, ה-LLM והסיווג.

Structured Outputs של Claude אוכף שהמודל יחזיר בדיוק את BotTurn,
כך שאין צורך ב-parsing ידני ואין סיכון לפלט לא תקין.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Timeline = Literal["immediate", "3_months", "6_12_months", "exploring", "unknown"]
Financing = Literal["cash", "mortgage_approved", "mortgage_needed", "unknown"]
Intent = Literal["buy", "sell", "invest", "browsing", "unknown"]
Engagement = Literal["high", "medium", "low"]
Stage = Literal["greeting", "intent", "qualification", "engagement", "cta", "handoff"]


class ExtractedParams(BaseModel):
    """הנתונים שהבוט מחלץ מהשיחה. כולם אופציונליים — מצטברים לאורך התורות."""

    budget_ils: Optional[int] = Field(None, description="אומדן תקציב נקודתי בש\"ח")
    timeline: Timeline = "unknown"
    financing: Financing = "unknown"
    intent: Intent = "unknown"
    has_property_to_sell: Optional[bool] = None
    area: Optional[str] = None
    rooms: Optional[int] = None
    engagement: Engagement = "medium"
    contact_name: Optional[str] = None
    phone: Optional[str] = None


class BotTurn(BaseModel):
    """הפלט המלא של תור אחד של הבוט."""

    reply: str = Field(description="הטקסט שמוצג ללקוח — בטון יוקרתי")
    stage: Stage
    extracted: ExtractedParams
    handoff_to_human: bool = Field(
        description="האם להעביר לסוכן אנושי (escape hatch)"
    )
    notes: str = Field(default="", description="הערה פנימית קצרה, לא מוצגת ללקוח")


class LeadScore(BaseModel):
    """תוצאת הסיווג הדטרמיניסטי."""

    score: float
    level: Literal["High", "Medium", "Low"]
    breakdown: dict[str, float]
