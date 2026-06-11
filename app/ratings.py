"""שמירת דירוגי לידים ופידבק שיחות — JSONBin.io (persistent)."""

import json
import os
import httpx
from datetime import datetime, timezone

JSONBIN_API = "https://api.jsonbin.io/v3"
JSONBIN_KEY = os.getenv("JSONBIN_KEY", "$2a$10$KoACzRcY64gqyT2LnOQ9UOG06ZE8gub8FZLzOm3B5nwUxz7mDEN92")

# Bin IDs - will be created on first use
RATINGS_BIN = os.getenv("RATINGS_BIN", "")
FEEDBACK_BIN = os.getenv("FEEDBACK_BIN", "")

_cache = {"ratings_bin": RATINGS_BIN, "feedback_bin": FEEDBACK_BIN}


def _create_bin(name: str) -> str:
    """יוצר bin חדש ב-JSONBin."""
    try:
        resp = httpx.post(
            f"{JSONBIN_API}/b",
            headers={
                "X-Master-Key": JSONBIN_KEY,
                "Content-Type": "application/json",
                "X-Bin-Name": name,
            },
            json=[],
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["metadata"]["id"]
    except:
        pass
    return ""


def _get_bin_id(name: str) -> str:
    """מחזיר bin ID, יוצר אם לא קיים."""
    key = f"{name}_bin"
    if _cache.get(key):
        return _cache[key]

    # Try to find existing bin
    try:
        resp = httpx.get(
            f"{JSONBIN_API}/bins",
            headers={"X-Master-Key": JSONBIN_KEY},
            timeout=15,
        )
        if resp.status_code == 200:
            for b in resp.json():
                if b.get("snippetMeta", {}).get("name") == name:
                    _cache[key] = b["id"]
                    return b["id"]
    except:
        pass

    # Create new bin
    bin_id = _create_bin(name)
    _cache[key] = bin_id
    return bin_id


def _load(name: str) -> list:
    """טוען נתונים מ-JSONBin."""
    bin_id = _get_bin_id(name)
    if not bin_id:
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
                return data
    except:
        pass
    return []


def _save(name: str, data: list) -> None:
    """שומר נתונים ל-JSONBin."""
    bin_id = _get_bin_id(name)
    if not bin_id:
        return
    try:
        httpx.put(
            f"{JSONBIN_API}/b/{bin_id}",
            headers={
                "X-Master-Key": JSONBIN_KEY,
                "Content-Type": "application/json",
            },
            json=data,
            timeout=15,
        )
    except:
        pass


def save_rating(session_id: str, color: str, profile: dict, transcript: list) -> None:
    """שמירת דירוג ליד."""
    records = _load("oren-ratings")
    records.append({
        "session_id": session_id,
        "color": color,
        "level": {"red": "ליד חם", "orange": "ליד בינוני", "green": "ליד קר"}[color],
        "profile": profile,
        "transcript": transcript,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save("oren-ratings", records)


def save_feedback(session_id: str, rating: str, notes: str, transcript: list = None) -> None:
    """שמירת פידבק על איכות השיחה."""
    records = _load("oren-feedback")
    records.append({
        "session_id": session_id,
        "rating": rating,
        "notes": notes,
        "transcript": transcript or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save("oren-feedback", records)


def get_all_ratings() -> list:
    return _load("oren-ratings")


def get_all_feedback() -> list:
    return _load("oren-feedback")
