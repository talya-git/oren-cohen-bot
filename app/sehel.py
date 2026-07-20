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

# ניתוב סוכנים
AGENT_HE = "aaron@orencohengroup.com"   # עברית → אהרון
AGENT_EN = "lisa@orencohengroup.com"    # אנגלית → ליסה
AGENT_YAD2 = "office@orencohengroup.com"  # יד 2 → בועז

# מיפוי שם פרויקט → project_id בשכל
PROJECT_MAP: dict[str, str] = {
    "ניתאי": "25049cf2-3546-438d-8654-d67a53a98a80",
    "סוקולוב": "d409ce62-c761-4570-beaf-f27bb6f84397",
    "סוקולוב 6": "d409ce62-c761-4570-beaf-f27bb6f84397",
    "טלביה פארק": "d409ce62-c761-4570-beaf-f27bb6f84397",
    "קרן היסוד": "bf030ff9-871a-4faf-a00c-93ead0aca9ab",
    "מאיר שחם": "514ce548-2ae3-4cf8-bd9a-1297ad4c25e8",
    "לינקולן": "cec6af9a-8987-4eb8-93f6-c0a7f9ee97d9",
    "אינדפנדס": "e567b50c-05b1-42da-b7ca-82aad861f157",
    "הנגיד": "7934f290-8d17-4622-a934-a04698569591",
    "שמואל הנגיד": "7934f290-8d17-4622-a934-a04698569591",
    "נוף הנגיד": "7934f290-8d17-4622-a934-a04698569591",
    "שמואל הנגיד רזידנס": "1a98e044-c291-4ce4-a374-c77257103903",
    "רזידנס": "1a98e044-c291-4ce4-a374-c77257103903",
    "תיבת האוצרות": "bddffc55-30b2-449d-b437-3acaaf7a983d",
    "בית הערבה": "c5d6647b-94a6-43dd-b628-2618bb6eac73",
    "עדן": "8f68faaf-9751-4230-b20a-e73bb0c39ae1",
    "יפו 184": "5f4cf862-9cf5-4867-889f-c36fed80be97",
    "יפו": "5f4cf862-9cf5-4867-889f-c36fed80be97",
    "השלושה": "9d52b0a5-616d-480f-9234-2056f821a8b6",
}
DEFAULT_PROJECT_ID = "fa149402-5c50-49f4-ba4e-bc94440f6806"  # אורן כהן יד 2 (ברירת מחדל)


def _resolve_project_id(area: str | None) -> str:
    """מחזיר project_id לפי שם הפרויקט/אזור שהוזכר בשיחה."""
    if not area:
        return DEFAULT_PROJECT_ID
    area_lower = area.lower()
    for key, pid in PROJECT_MAP.items():
        if key in area_lower or area_lower in key:
            return pid
    return DEFAULT_PROJECT_ID


def _is_projects_division(project_name: str | None, agent_name: str = "") -> bool:
    """מחזיר True אם הליד שייך למחלקת פרויקטים (פרויקט ספציפי מהרשימה)."""
    if not project_name:
        return False
    name_lower = project_name.lower()
    return any(key in name_lower or name_lower in key for key in PROJECT_MAP)

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


def _build_comment(
    p: ExtractedParams,
    level: str,
    score: float,
    agent_color: str | None,
    transcript: list[dict] | None = None,
) -> str:
    city_area = " | ".join(filter(None, [p.city, p.neighborhood, p.area]))
    lines = [
        f"סוכן וירטואלי (דניאל) | דירוג אוטומטי: {level} ({score})",
        f"כוונה: {_INTENT_HE.get(p.intent, '—')} | סוג נכס: {p.property_type or '—'} | חדרים: {p.rooms or '—'}",
        f"אזור: {city_area or '—'}",
        "תקציב: {} ש\"ח | לו\"ז: {} | מימון: {}".format(
            f"{p.budget_ils:,}" if p.budget_ils else "—",
            _TIMELINE_HE.get(p.timeline, "—"),
            _FINANCING_HE.get(p.financing, "—"),
        ),
    ]
    if agent_color:
        lines.append(f"דירוג סוכן: {_COLOR_HE.get(agent_color, agent_color)}")
    if transcript:
        lines.append("\n--- תמליל שיחה ---")
        for msg in transcript:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant":
                # חלץ רק את ה-reply מה-JSON של הבוט
                try:
                    import json as _json
                    parsed = _json.loads(content)
                    content = parsed.get("reply", content)
                except Exception:
                    pass
            if role in ("user", "assistant") and content and not content.startswith("[הקשר:"):
                prefix = "לקוח" if role == "user" else "דניאל"
                lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def build_payload(
    profile: ExtractedParams,
    level: str,
    score: float,
    *,
    language: str = "he",
    media_source: str = "Facebook",
    agent_color: str | None = None,
    project_id: str | None = None,
    is_projects: bool | None = None,
    transcript: list[dict] | None = None,
    no_response: bool = False,
) -> dict:
    """ממפה את הליד שלנו למבנה ששכל מצפה לו. מעלה ValueError אם חסר טלפון."""
    if not profile.phone:
        raise ValueError("חסר טלפון — שכל דורש lead_phone.")

    # קביעת מחלקה: אם is_projects לא הועבר — נסיק לפי האזור
    if is_projects is None:
        is_projects = _is_projects_division(profile.area)

    if is_projects:
        agent = AGENT_HE if language == "he" else AGENT_EN
        resolved_pid = project_id or PROJECT_ID or _resolve_project_id(profile.area)
    else:
        agent = AGENT_YAD2
        resolved_pid = DEFAULT_PROJECT_ID

    tags = [_LEVEL_TAG.get(level, level)]
    if not is_projects:
        tags.append("מתעניין בנכס יד 2")
    if no_response:
        tags.append("אין מענה")

    payload: dict = {
        "project_id": resolved_pid,
        "lead_phone": profile.phone,
        "media_source": media_source,
        "lead_comment": _build_comment(profile, level, score, agent_color, transcript),
        "tags[]": tags,
        "agentUsername": agent,
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
