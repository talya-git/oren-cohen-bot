"""שמירת דירוגי לידים ופידבק שיחות — JSONBin.io (persistent)."""

import json
import os
import httpx
from datetime import datetime, timezone

JSONBIN_API = "https://api.jsonbin.io/v3"
JSONBIN_KEY = os.getenv("JSONBIN_KEY", "$2a$10$KoACzRcY64gqyT2LnOQ9UOG06ZE8gub8FZLzOm3B5nwUxz7mDEN92")

# Bin IDs
RATINGS_BIN = "6a2a95b3da38895dfeacbd8a"
FEEDBACK_BIN = "6a2a95b3f5f4af5e29de4696"

def _load(bin_id: str) -> list:
    """טוען נתונים מ-JSONBin."""
    if not JSONBIN_KEY or not bin_id:
        return []
    try:
        resp = httpx.get(
            f"{JSONBIN_API}/b/{bin_id}/latest",
            headers={"X-Master-Key": JSONBIN_KEY},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json().get("record", [])
            if isinstance(data, list):
                # Filter out init record
                return [d for d in data if not d.get("init")]
    except:
        pass
    return []


def _save(bin_id: str, data: list) -> None:
    """שומר נתונים ל-JSONBin."""
    if not JSONBIN_KEY or not bin_id:
        print(f"[SAVE] No key or bin_id: key={bool(JSONBIN_KEY)}, bin={bin_id}")
        return
    try:
        resp = httpx.put(
            f"{JSONBIN_API}/b/{bin_id}",
            headers={
                "X-Master-Key": JSONBIN_KEY,
                "Content-Type": "application/json",
            },
            json=data,
            timeout=15,
        )
        print(f"[SAVE] bin={bin_id} status={resp.status_code} items={len(data)}")
    except Exception as e:
        print(f"[SAVE] ERROR: {e}")


def save_rating(session_id: str, color: str, profile: dict, transcript: list) -> None:
    """שמירת דירוג ליד."""
    records = _load(RATINGS_BIN)
    records.append({
        "session_id": session_id,
        "color": color,
        "level": {"red": "ליד חם", "orange": "ליד בינוני", "green": "ליד קר"}[color],
        "profile": profile,
        "transcript": transcript,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(RATINGS_BIN, records)


def save_feedback(session_id: str, rating: str, notes: str, transcript: list = None) -> None:
    """שמירת פידבק על איכות השיחה."""
    records = _load(FEEDBACK_BIN)
    records.append({
        "session_id": session_id,
        "rating": rating,
        "notes": notes,
        "transcript": transcript or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(FEEDBACK_BIN, records)


def get_all_ratings() -> list:
    return _load(RATINGS_BIN)


def get_all_feedback() -> list:
    return _load(FEEDBACK_BIN)
