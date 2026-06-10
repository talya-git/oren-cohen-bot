"""שמירת דירוגי לידים ופידבק שיחות."""

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RATINGS_FILE = DATA_DIR / "ratings.json"
FEEDBACK_FILE = DATA_DIR / "feedback.json"


def _load(file: Path) -> list:
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    return []


def _save(file: Path, data: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_rating(session_id: str, color: str, profile: dict, transcript: list) -> None:
    """שמירת דירוג ליד."""
    records = _load(RATINGS_FILE)
    records.append({
        "session_id": session_id,
        "color": color,
        "level": {"red": "ליד חם", "orange": "ליד בינוני", "green": "ליד קר"}[color],
        "profile": profile,
        "transcript": transcript,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(RATINGS_FILE, records)


def save_feedback(session_id: str, rating: str, notes: str) -> None:
    """שמירת פידבק על איכות השיחה."""
    records = _load(FEEDBACK_FILE)
    records.append({
        "session_id": session_id,
        "rating": rating,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(FEEDBACK_FILE, records)


def get_all_ratings() -> list:
    return _load(RATINGS_FILE)


def get_all_feedback() -> list:
    return _load(FEEDBACK_FILE)
