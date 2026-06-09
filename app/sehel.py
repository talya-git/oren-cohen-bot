"""אינטגרציה ל-CRM "שכל" — הזרקת לידים מסווגים.

ה-API של שכל: POST יחיד ל-https://leads.sehel.co.il עם project_id בגוף הבקשה.
תיעוד: https://crm.sehel.co.il/docs/

אין בשכל שדה ייעודי לציון/סיווג, ולכן:
- את ה-data של הסיווג (תקציב, לו"ז, מימון...) שמים ב-lead_comment (טקסט חופשי).
- את רמת הליד שמים כ-tag, כדי שאפשר לסנן ב-CRM.

שתי דרכי שליחה (אותה פונקציה):
- ברירת מחדל: POST ישיר ל-שכל (צריך SEHEL_PROJECT_ID).
- אם מוגדר SEHEL_WEBHOOK_URL: שולח לשם במקום (תרחיש Make/Zapier).
"""

import os

import httpx

from .schemas import ExtractedParams

SEHEL_URL = os.getenv("SEHEL_URL", "https://leads.sehel.co.il")
PROJECT_ID = os.getenv("SEHEL_PROJECT_ID")
WEBHOOK_URL = os.getenv("SEHEL_WEBHOOK_URL")  # אופציונלי — מסלול Make/Zapier

# תוויות עבריות קריאות לסוכן ב-CRM
_INTENT_HE = {
    "buy": "קנייה",
    "sell": "מכירה",
    "invest": "השקעה",
    "browsing": "מתעניין",
    "unknown": "לא ידוע",
}
_TIMELINE_HE = {
    "immediate": "מיידי",
    "3_months": "שלושה חודשים",
    "6_12_months": "חצי שנה עד שנה",
    "exploring": "בבירור ראשוני",
    "unknown": "לא ידוע",
}
_FINANCING_HE = {
    "cash": "הון עצמי",
    "mortgage_approved": "משכנתא מאושרת",
    "mortgage_needed": "זקוק למשכנתא",
    "unknown": "לא ידוע",
}
_LEVEL_TAG = {"High": "ליד חם", "Medium": "ליד בינוני", "Low": "ליד קר"}
_COLOR_HE = {"red": "אדום", "orange": "כתום", "green": "ירוק"}


def _build_comment(p: ExtractedParams, level: str, score: float, agent_color: str | None) -> str:
    lines = [
        f"סוכן וירטואלי (דניאל) | דירוג אוטומטי: {level} ({score})",
        f"תקציב: {p.budget_ils or '—'} | לו\"ז: {_TIMELINE_HE.get(p.timeline, '—')}"
        f" | מימון: {_FINANCING_HE.get(p.financing, '—')}",
        f"כוונה: {_INTENT_HE.get(p.intent, '—')} | אזור: {p.area or '—'}"
        f" | חדרים: {p.rooms or '—'}",
    ]
    if agent_color:
        lines.append(f"דירוג סוכן: {_COLOR_HE.get(agent_color, agent_color)}")
    return "\n".join(lines)


def build_payload(
    profile: ExtractedParams,
    level: str,
    score: float,
    *,
    media_source: str = "Facebook",
    agent_color: str | None = None,
    project_id: str | None = None,
) -> dict:
    """ממפה את הליד שלנו למבנה ששכל מצפה לו. מעלה ValueError אם חסר טלפון."""
    if not profile.phone:
        raise ValueError("חסר טלפון — שכל דורש lead_phone. נדרש לאסוף טלפון לפני הזרקה.")

    payload: dict = {
        "project_id": project_id or PROJECT_ID,
        "lead_phone": profile.phone,
        "media_source": media_source,
        "lead_comment": _build_comment(profile, level, score, agent_color),
        "tags": [_LEVEL_TAG.get(level, level)],
    }
    if profile.contact_name:
        payload["lead_name"] = profile.contact_name
    return payload


def push_lead(payload: dict, *, dry_run: bool = False) -> dict:
    """שולח את הליד לשכל (או ל-webhook של Make/Zapier אם הוגדר).

    dry_run=True מחזיר את ה-payload בלי לשלוח — שימושי לבדיקה.
    """
    if dry_run:
        return {"dry_run": True, "target": WEBHOOK_URL or SEHEL_URL, "payload": payload}

    if not payload.get("project_id") and not WEBHOOK_URL:
        raise RuntimeError("חסר SEHEL_PROJECT_ID (או SEHEL_WEBHOOK_URL).")

    target = WEBHOOK_URL or SEHEL_URL
    resp = httpx.post(target, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # תצוגה מקדימה (dry-run) — מראה בדיוק מה ייושלח לשכל, בלי לשלוח בפועל
    import json

    sample = ExtractedParams(
        budget_ils=8_000_000,
        timeline="6_12_months",
        financing="cash",
        intent="buy",
        area="רחביה",
        rooms=5,
        engagement="high",
        contact_name="ישראל ישראלי",
        phone="0525228080",
    )
    preview = push_lead(
        build_payload(sample, "High", 0.87, media_source="Facebook", agent_color="green"),
        dry_run=True,
    )
    print(json.dumps(preview, ensure_ascii=False, indent=2))
