"""שליחת הודעות WhatsApp דרך UltraMsg."""

import asyncio
import time
import requests

from . import sehel

INSTANCE_ID = "instance183747"
TOKEN = "3mfx8x4sw1bv4496"
BASE_URL = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"

TEST_PHONES = [
    "+972526239608",
    "+13055863760",
    "+972504183337",
]

NO_RESPONSE_HOURS = 24


def send_message(phone: str, message: str) -> dict:
    resp = requests.post(BASE_URL, data={
        "token": TOKEN,
        "to": phone,
        "body": message,
        "priority": 10,
    }, verify=False)
    return resp.json()


def send_test():
    for phone in TEST_PHONES:
        result = send_message(phone, "היי, אני דניאל ממשרד אורן כהן גרופ 😊")
        print(f"{phone} → {result}")
        time.sleep(2)


# === FastAPI router ===
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

_wa_sessions: dict = {}
_wa_done: set[str] = set()
_wa_seen_sids: set[str] = set()
_wa_no_response_tasks: dict[str, asyncio.Task] = {}
_wa_original_project: dict[str, str] = {}
_wa_is_projects: dict[str, bool] = {}
_wa_is_reengagement: dict[str, bool] = {}


def _detect_language(phone: str, name: str | None) -> str:
    if phone.lstrip("+").startswith("972"):
        if name and any("\u05d0" <= c <= "\u05ea" for c in name):
            return "he"
        return "en"
    return "en"


def start_reengagement(phone: str, name: str | None, project_name: str, agent_name: str = "") -> None:
    """שולח הודעת פתיחה ללקוח ישן ומאתחל session."""
    from .engine import Conversation

    normalized = phone.lstrip("+")
    if name:
        try:
            fixed = name.encode("latin1").decode("utf-8")
            if any("\u05d0" <= c <= "\u05ea" for c in fixed):
                name = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    lang = _detect_language(phone, name)
    is_projects = sehel._is_projects_division(project_name, agent_name)
    # project_name רלוונטי רק אם הוא פרויקט ספציפי מהרשימה
    pname_for_convo = project_name if is_projects else None
    convo = Conversation(language=lang, project_name=pname_for_convo)

    if name:
        convo.profile.contact_name = name
    convo.profile.phone = f"+{normalized}"

    original_pid = sehel._resolve_project_id(project_name)
    _wa_original_project[normalized] = original_pid
    _wa_is_projects[normalized] = is_projects
    _wa_is_reengagement[normalized] = True
    _wa_sessions[normalized] = convo

    division = "פרויקטים" if is_projects else "יד 2"
    print(f"[INBOUND] {phone} | {name} | פרויקט: {project_name!r} | מחלקה: {division}")

    if lang == "en":
        greeting = (
            f"Hi{' ' + name if name else ''},\n"
            f"This is Daniel from Oren Cohen Group in Jerusalem.\n"
            f"I'm reaching out following your previous inquiry to our office. "
            f"We are currently putting together a number of exclusive real estate opportunities in upcoming Jerusalem projects, "
            f"on terms not available to the general public.\n"
            f"Since you were looking for something similar in the past, I thought it would be right to update you before anyone else.\n"
            f"Is this still relevant for you?"
        )
    else:
        greeting = (
            f"היי{' ' + name if name else ''},\n"
            f"כאן דניאל מאורן כהן גרופ בירושלים.\n"
            f"אני פונה אליך בהמשך לפנייתך למשרדנו בעבר. "
            f"בימים אלו אנחנו מרכזים עבור לקוחותינו מספר הזדמנויות נדל\"ן מיוחדות בפרויקטים עתידיים בירושלים "
            f"בתנאים אטרקטיביים שלא מוצעים לציבור הרחב.\n"
            f"מאחר וחיפשת משהו דומה בעבר, חשבתי שנכון יהיה לעדכן אותך לפני כולם.\n"
            f"האם הנושא עדיין רלוונטי עבורך?"
        )

    convo.messages.append({"role": "assistant", "content": greeting})
    print(f"[GREETING] phone={normalized} name={name!r} lang={lang} project={pname_for_convo!r}")
    send_message(f"+{normalized}", greeting)


async def _no_response_timer(phone: str):
    await asyncio.sleep(NO_RESPONSE_HOURS * 3600)
    convo = _wa_sessions.get(phone)
    if not convo or not convo.profile.phone:
        return
    dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
    try:
        is_projects = _wa_is_projects.get(phone, False)
        payload = sehel.build_payload(
            convo.profile, "Low", 0.0,
            is_projects=is_projects,
            transcript=convo.messages,
            no_response=True,
            media_source="WhatsApp",
        )
        sehel.push_lead(payload, dry_run=dry)
    except Exception:
        pass


# ביטויים לזיהוי כוונה
_NOT_RELEVANT = ["לא רלוונטי", "לא מעוניין", "לא רלוונט", "לא מתעניין", "לא צריך", "לא רוצה", "not relevant", "not interested"]
_SNOOZE_WEEK = ["עסוק", "אחר כך", "אחרי", "יחשוב", "אחשוב", "לא עכשיו", "busy", "later", "will think", "not now"]


def _classify_response(msg: str) -> str:
    lower = msg.lower()
    if any(p in lower for p in _NOT_RELEVANT):
        return "not_relevant"
    if any(p in lower for p in _SNOOZE_WEEK):
        return "snooze_week"
    return "continue"


def _save_followup(phone: str, weeks: int, reason: str) -> None:
    from datetime import datetime, timezone, timedelta
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "data" / "followups.json"
    records = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    records.append({
        "phone": phone,
        "reason": reason,
        "followup_after": (datetime.now(timezone.utc) + timedelta(weeks=weeks)).isoformat(),
    })
    f.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    from .engine import Conversation
    from . import database as _db
    from .scoring import score_lead

    data = await request.json()
    msg = data.get("data") or data
    phone = msg.get("from", "").replace("@c.us", "").replace("+", "")
    text = msg.get("body", "").strip()
    msg_sid = str(msg.get("id", ""))

    if msg_sid and msg_sid in _wa_seen_sids:
        return {"status": "duplicate"}
    if msg_sid:
        _wa_seen_sids.add(msg_sid)

    if not phone or not text or msg.get("fromMe"):
        return {"status": "ignored"}

    # שיחה שכבר הסתיימה
    if phone in _wa_done or _db.is_conversation_done(phone):
        import openai as _oai
        try:
            _resp = _oai.OpenAI().chat.completions.create(
                model="gpt-4o-mini", max_tokens=80,
                messages=[
                    {"role": "system", "content": (
                        "אתה דניאל מאורן כהן גרופ. השיחה הסתיימה והלקוח הועבר לסוכן אנושי. "
                        "תשובה קצרה ומנומסת בלבד."
                    )},
                    {"role": "user", "content": text}
                ]
            )
            reply = _resp.choices[0].message.content.strip()
        except Exception:
            reply = "הסוכן יצור איתך קשר תוך יום עסקים."
        send_message(f"+{phone}", reply)
        return {"status": "done_reply"}

    # אם אין session — תשובה להודעת re-engagement
    if phone not in _wa_sessions:
        intent = _classify_response(text)
        if intent == "not_relevant":
            _save_followup(phone, weeks=26, reason="not_relevant")
            send_message(f"+{phone}", "מובן, תודה על התשובה! אם בעתיד תתעניין — אנחנו כאן 😊")
            return {"status": "snoozed_26w"}
        if intent == "snooze_week":
            _save_followup(phone, weeks=1, reason="snooze")
            send_message(f"+{phone}", "בטח, אחזור אליך בשבוע הבא! 😊")
            return {"status": "snoozed_1w"}
        conv = Conversation()
        conv.messages.append({
            "role": "user",
            "content": f"[הקשר: הלקוח קיבל הודעת re-engagement ועונה שהוא מעוניין. תגובתו: '{text}'. המשך ישירות לשאלת הצרכים.]"
        })
        conv.messages.append({
            "role": "assistant",
            "content": '{"reply": "", "stage": "intent", "extracted": {}, "handoff_to_human": false, "notes": "re-engagement context injected"}'
        })
        _wa_sessions[phone] = conv

    convo = _wa_sessions[phone]
    turn, score = convo.send(text)
    time.sleep(7)
    send_message(f"+{phone}", turn.reply)

    if turn.handoff_to_human:
        _wa_done.add(phone)
        dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
        is_projects = _wa_is_projects.get(phone, False)
        try:
            payload = sehel.build_payload(
                convo.profile, score.level, score.score,
                language=getattr(convo, "_language", "he"),
                media_source="WhatsApp",
                is_projects=is_projects,
                transcript=convo.messages,
            )
            sehel.push_lead(payload, dry_run=dry)
        except Exception as e:
            print(f"[SEHEL ERROR] {e}")
        del _wa_sessions[phone]

    return {"status": "ok"}


if __name__ == "__main__":
    send_test()
