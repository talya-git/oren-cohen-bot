"""
בוט בקרה — סורק את כל הערוצים ומוודא שלידים נכנסו לשכל ולטיפול סוכן.

בודק כל X דקות:
1. לידים מ-WhatsApp/מייל/ניוזלטר שלא נדחפו לשכל
2. לידים בשכל שלא הוקצו לסוכן
3. סוכנים שלא ענו לליד שהוקצה להם — שולח תזכורת + ביקורת למנהל
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from . import database as db
from . import sehel as _sehel

# ---- הגדרות ----
CHECK_INTERVAL_MINUTES = int(os.getenv("CONTROL_BOT_INTERVAL_MINUTES", "30"))
NO_RESPONSE_HOURS = int(os.getenv("CONTROL_BOT_NO_RESPONSE_HOURS", "4"))
NO_ASSIGN_HOURS = int(os.getenv("CONTROL_BOT_NO_ASSIGN_HOURS", "2"))

MANAGER_EMAIL = os.getenv("MANAGER_EMAIL", "naomi@orencohengroup.com")
MANAGER_PHONE = os.getenv("MANAGER_PHONE", "+972528962040")

AGENT_PHONES: dict[str, str] = {
    "יניב":   "+972545596052",
    "משה":    "+972523873383",
    "מירי":   "+972543402018",
    "מיכאל":  "+972584114686",
    "רבקה":   "+972586455059",
    "אלחנן":  "+972549183150",
    "אורן":   "+972549183150",
    "אריה":   "+972552704922",
    "בועז":   "+972545596052",
    "אהרון":  "+972549183150",
    "ליסה":   "+13055863760",
    "דב":     "+972526239608",
    "נעמי":   "+972515528956",
    "אייזיק": "+972535226105",
    "רמי":    "+972542315410",
    "נתנאל":  "+972545596052",
}

AGENT_EMAILS: dict[str, str] = {
    "יניב":   "yaniv@orencohengroup.com",
    "משה":    "moshe@orencohengroup.com",
    "מירי":   "miri@orencohengroup.com",
    "מיכאל":  "michael@orencohengroup.com",
    "רבקה":   "rivka@orencohengroup.com",
    "אלחנן":  "elchanan@orencohengroup.com",
    "אורן":   "oren@orencohengroup.com",
    "אריה":   "aryeh@orencohengroup.com",
    "בועז":   "office@orencohengroup.com",
    "אהרון":  "aaron@orencohengroup.com",
    "ליסה":   "lisa@orencohengroup.com",
    "דב":     "dovr@orencohengroup.com",
    "נעמי":   "naomi@orencohengroup.com",
}

EMAIL_TO_NAME: dict[str, str] = {v: k for k, v in AGENT_EMAILS.items()}

# מעקב אחרי התראות שכבר נשלחו (למניעת ספאם)
_alerted_leads: set[str] = set()
_alerted_no_assign: set[int] = set()


def _send_wa(phone: str, msg: str) -> None:
    """שולח הודעת WhatsApp."""
    try:
        from .whatsapp import send_message
        send_message(phone, msg)
    except Exception as e:
        print(f"[CONTROL BOT WA ERROR] {phone}: {e}")


def _send_email_alert(to: str, subject: str, body: str) -> None:
    """שולח מייל התראה."""
    try:
        from .mailer import send_email
        send_email(to=to, subject=subject, body=body)
    except Exception as e:
        print(f"[CONTROL BOT EMAIL ERROR] {to}: {e}")


def _hours_since(ts_str: Optional[str]) -> float:
    """מחשב כמה שעות עברו מאז timestamp."""
    if not ts_str:
        return 0.0
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        return delta.total_seconds() / 3600
    except Exception:
        return 0.0


# ---- בדיקה 1: לידים שלא נכנסו לשכל ----

def check_unsynced_to_sehel() -> int:
    """
    בודק לידים מ-reengagement_sent שענו חיובי (replied=True)
    אבל לא נדחפו לשכל (stalled_pushed=False) ועברו יותר מ-NO_RESPONSE_HOURS שעות.
    שולח התראה למנהל.
    """
    dry = not (_sehel.PROJECT_ID or _sehel.WEBHOOK_URL)
    count = 0
    try:
        rows = db.get_stalled_conversations(hours=NO_RESPONSE_HOURS)
        for row in rows:
            phone = row.get("phone", "")
            if not phone or phone.startswith("email:"):
                continue
            key = f"sehel:{phone}"
            if key in _alerted_leads:
                continue

            name = row.get("client_name") or phone
            agent_email = row.get("agent_email") or ""
            agent_name = EMAIL_TO_NAME.get(agent_email, agent_email)
            hours = _hours_since(row.get("sent_at"))

            print(f"[CONTROL BOT] ליד לא נכנס לשכל: {name} ({phone}) | סוכן: {agent_name} | {hours:.1f} שעות")

            # שלח התראה למנהל
            msg = (
                f"⚠️ בקרה: ליד לא נכנס לשכל!\n"
                f"שם: {name}\n"
                f"טלפון: {phone}\n"
                f"סוכן: {agent_name}\n"
                f"עבר {hours:.0f} שעות מאז השיחה"
            )
            if MANAGER_PHONE:
                _send_wa(MANAGER_PHONE, msg)

            _alerted_leads.add(key)
            count += 1
    except Exception as e:
        print(f"[CONTROL BOT] check_unsynced_to_sehel error: {e}")
    return count


# ---- בדיקה 2: לידים בשכל שלא הוקצו לסוכן ----

def check_unassigned_leads() -> int:
    """
    בודק לידים ב-DB עם status='new' שעברו יותר מ-NO_ASSIGN_HOURS שעות.
    שולח התראה למנהל.
    """
    count = 0
    try:
        all_leads = db.get_all_leads()
        for lead in all_leads:
            if lead.get("status") not in ("new", None):
                continue
            if lead.get("assigned_to"):
                continue
            lead_id = lead.get("id")
            if lead_id in _alerted_no_assign:
                continue
            hours = _hours_since(lead.get("created_at"))
            if hours < NO_ASSIGN_HOURS:
                continue

            name = lead.get("contact_name") or f"ליד #{lead_id}"
            phone = lead.get("phone") or ""
            source = (lead.get("notes") or "").replace("source:", "")

            print(f"[CONTROL BOT] ליד לא הוקצה: {name} ({phone}) | {hours:.1f} שעות | מקור: {source}")

            msg = (
                f"⚠️ בקרה: ליד לא הוקצה לסוכן!\n"
                f"שם: {name}\n"
                f"טלפון: {phone}\n"
                f"מקור: {source or 'לא ידוע'}\n"
                f"עבר {hours:.0f} שעות מאז הכניסה"
            )
            if MANAGER_PHONE:
                _send_wa(MANAGER_PHONE, msg)

            _alerted_no_assign.add(lead_id)
            count += 1
    except Exception as e:
        print(f"[CONTROL BOT] check_unassigned_leads error: {e}")
    return count


# ---- בדיקה 3: סוכנים שלא נתנו מענה ----

def check_agent_no_response() -> int:
    """
    בודק לידים שהוקצו לסוכן (status='assigned') ועברו יותר מ-NO_RESPONSE_HOURS שעות
    ללא עדכון (updated_at לא השתנה).
    שולח תזכורת לסוכן + ביקורת למנהל.
    """
    count = 0
    try:
        all_leads = db.get_all_leads()
        for lead in all_leads:
            if lead.get("status") != "assigned":
                continue
            lead_id = lead.get("id")
            key = f"agent_no_resp:{lead_id}"
            if key in _alerted_leads:
                continue

            hours = _hours_since(lead.get("updated_at") or lead.get("created_at"))
            if hours < NO_RESPONSE_HOURS:
                continue

            name = lead.get("contact_name") or f"ליד #{lead_id}"
            phone = lead.get("phone") or ""
            agent_name = lead.get("agent_name") or ""
            agent_phone = AGENT_PHONES.get(agent_name)
            agent_email = AGENT_EMAILS.get(agent_name)

            print(f"[CONTROL BOT] סוכן לא ענה: {agent_name} | ליד: {name} ({phone}) | {hours:.1f} שעות")

            # תזכורת לסוכן
            reminder = (
                f"🔔 תזכורת: יש ליד שממתין לטיפולך!\n"
                f"שם: {name}\n"
                f"טלפון: {phone}\n"
                f"עבר {hours:.0f} שעות מאז ההקצאה\n"
                f"אנא צור קשר בהקדם."
            )
            if agent_phone:
                _send_wa(agent_phone, reminder)
            if agent_email:
                _send_email_alert(
                    to=agent_email,
                    subject=f"🔔 תזכורת: ליד ממתין לטיפולך — {name}",
                    body=reminder,
                )

            # ביקורת למנהל
            manager_msg = (
                f"🚨 ביקורת: סוכן לא נתן מענה לליד!\n"
                f"סוכן: {agent_name}\n"
                f"ליד: {name} ({phone})\n"
                f"עבר {hours:.0f} שעות ללא טיפול"
            )
            if MANAGER_PHONE:
                _send_wa(MANAGER_PHONE, manager_msg)
            if MANAGER_EMAIL:
                _send_email_alert(
                    to=MANAGER_EMAIL,
                    subject=f"🚨 ביקורת: {agent_name} לא טיפל בליד {name}",
                    body=manager_msg,
                )

            _alerted_leads.add(key)
            count += 1
    except Exception as e:
        print(f"[CONTROL BOT] check_agent_no_response error: {e}")
    return count


# ---- לולאה ראשית ----

async def run_control_bot():
    """לולאה ראשית של בוט הבקרה — רצה כל CHECK_INTERVAL_MINUTES דקות."""
    print(f"[CONTROL BOT] מתחיל | בדיקה כל {CHECK_INTERVAL_MINUTES} דקות")
    while True:
        try:
            n1 = check_unsynced_to_sehel()
            n2 = check_unassigned_leads()
            n3 = check_agent_no_response()
            if n1 + n2 + n3 > 0:
                print(f"[CONTROL BOT] נמצאו: {n1} לא בשכל | {n2} לא הוקצו | {n3} ללא מענה סוכן")
        except Exception as e:
            print(f"[CONTROL BOT ERROR] {e}")
        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)


def run_check_now() -> dict:
    """הרצה ידנית חד-פעמית — מחזיר סיכום."""
    n1 = check_unsynced_to_sehel()
    n2 = check_unassigned_leads()
    n3 = check_agent_no_response()
    return {
        "unsynced_to_sehel": n1,
        "unassigned_leads": n2,
        "agent_no_response": n3,
        "total_alerts": n1 + n2 + n3,
    }
