"""סכמות Pydantic — מאגר הפידבק — דירוג ליד בסוף שיחה.
אדום = High (רציני מאוד)
כתום = Medium
ירוק = Low
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"

# הגדרת הצבעים לפי הדרישה שלך: אדום הוא הרציני ביותר
Color = Literal["red", "orange", "green"]

# מיפוי צבע → רמת סיווג (כאן הגדרנו שאדום = High)
COLOR_TO_LEVEL: dict[str, str] = {"red": "High", "orange": "Medium", "green": "Low"}
COLOR_EMOJI: dict[str, str] = {"red": "🔴", "orange": "🟠", "green": "🟢"}


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # תוצרי השיחה
    transcript: list[dict]
    bot_level: str
    bot_score: float
    profile: dict

    # דירוג הסוכן (ממולא לאחר סיום השיחה)
    agent_color: Optional[Color] = None
    agent_id: Optional[str] = None
    notes: str = ""


def _load_raw() -> list[dict]:
    if not SESSIONS_FILE.exists():
        return []
    return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))


def _save_raw(records: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SESSIONS_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_all() -> list[SessionRecord]:
    return [SessionRecord(**r) for r in _load_raw()]


def save_session(
    *, transcript: list[dict], bot_level: str, bot_score: float, profile: dict
) -> SessionRecord:
    """נשמר בסיום שיחה; ממתין לדירוג צבע על ידי סוכן."""
    rec = SessionRecord(
        transcript=transcript,
        bot_level=bot_level,
        bot_score=bot_score,
        profile=profile,
    )
    records = _load_raw()
    records.append(rec.model_dump())
    _save_raw(records)
    return rec


def update_agent_rating(session_id: str, color: Color, notes: str = "") -> None:
    """עדכון הדירוג לאחר שהסוכן קבע את הצבע."""
    records = _load_raw()
    for r in records:
        if r["id"] == session_id:
            r["agent_color"] = color
            r["notes"] = notes
            break
    _save_raw(records)


def list_pending() -> list[SessionRecord]:
    return [r for r in load_all() if r.agent_color is None]