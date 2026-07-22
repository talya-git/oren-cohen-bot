"""שליחת הודעות WhatsApp דרך Twilio."""

import asyncio
import os
import time
import requests

from . import sehel

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

TEST_PHONES = [
    "+972526239608",
    "+13055863760",
    "+972504183337",
]

NO_RESPONSE_HOURS = 24


def send_message(phone: str, message: str) -> dict:
    to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
        data={"From": TWILIO_FROM, "To": to, "Body": message},
        auth=(TWILIO_SID, TWILIO_TOKEN),
    )
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
_wa_pilot_log: list[dict] = []  # לוג פיילוט בזיכרון


def _detect_language(phone: str, name: str | None) -> str:
    if phone.lstrip("+").startswith("972") or phone.startswith("05"):
        return "he"
    return "en"


def start_reengagement(phone: str, name: str | None, project_name: str, agent_name: str = "") -> None:
    """שולח הודעת פתיחה ללקוח ישן ומאתחל session."""
    from .engine import Conversation

    normalized = phone.lstrip("+")
    # נרמול מספר ישראלי
    if normalized.startswith("05"):
        normalized = "972" + normalized[1:]
    if name:
        try:
            fixed = name.encode("latin1").decode("utf-8")
            if any("\u05d0" <= c <= "\u05ea" for c in fixed):
                name = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    lang = _detect_language(phone, name)
    is_projects = sehel._is_projects_division(project_name, agent_name)
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

    # שמירה ב-DB
    from . import database as _db
    agent_email = _wa_is_projects.get(normalized) and "aaron@orencohengroup.com" or "office@orencohengroup.com"
    _db.mark_reengagement_sent(f"+{normalized}", name or "", agent_email)

    # רשום ללוג פיילוט
    _wa_pilot_log.append({
        "phone": f"+{normalized}",
        "name": name or "",
        "project": pname_for_convo or "",
        "sent": True,
        "replied": False,
        "handoff": False,
        "score": None,
        "notes": "",
    })


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

    # Twilio שולח form data
    form = await request.form()
    phone = str(form.get("From", "")).replace("whatsapp:", "").replace("+", "")
    text = str(form.get("Body", "")).strip()
    msg_sid = str(form.get("MessageSid", ""))

    if msg_sid and msg_sid in _wa_seen_sids:
        return {"status": "duplicate"}
    if msg_sid:
        _wa_seen_sids.add(msg_sid)

    if not phone or not text:
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

    # עדכון לוג פיילוט
    log_entry = next((e for e in _wa_pilot_log if e["phone"] == f"+{phone}"), None)
    if log_entry:
        log_entry["replied"] = True
        if turn.handoff_to_human:
            log_entry["handoff"] = True
            log_entry["score"] = score.level
            log_entry["notes"] = turn.notes or ""

    # עדכון replied ב-DB עם תמליל
    import json as _json
    transcript_text = "\n".join(
        f"{'דניאל' if m['role'] == 'assistant' else 'לקוח'}: {m['content']}"
        for m in convo.messages
        if m.get('role') in ('assistant', 'user') and not m['content'].startswith('[')
    )
    _db.update_reengagement_replied(f"+{phone}", True, transcript_text)

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


@router.post("/notify-agent")
async def notify_agent(request: Request):
    """נקרא מה-Tampermonkey אחרי שליחת batch — יוצר batch ב-DB ושולח הודעת אישור לסוכן."""
    from . import database as _db
    data = await request.json()
    agent_email = data.get("agent_email", "")
    agent_label = data.get("agent_label", "")
    phones = data.get("phones", [])  # רשימת הטלפונים שנשלחו

    if not agent_email:
        return {"status": "error", "reason": "no agent_email"}

    batch_id = _db.create_reengagement_batch(agent_email, agent_label)

    # עדכון batch_id לכל הרשומות שנשלחו זה עתה
    conn = _db.get_db()
    cur = conn.cursor()
    for phone in phones:
        cur.execute(
            f"UPDATE reengagement_sent SET batch_id={_db.PH} WHERE phone={_db.PH} AND batch_id IS NULL",
            (batch_id, phone)
        )
    conn.commit()
    conn.close()

    return {"status": "ok", "batch_id": batch_id}

@router.get("/sent-phones")
async def sent_phones(agent_email: str):
    from . import database as _db
    phones = _db.get_sent_phones(agent_email)
    return {"phones": list(phones)}


@router.get("/reengagement-results")
async def reengagement_results(agent_email: str):
    from . import database as _db
    return {"results": _db.get_reengagement_results(agent_email)}


@router.get("/pilot-results")
async def pilot_results():
    """מחזיר את לוג הפיילוט הנוכחי."""
    return {"results": _wa_pilot_log}


@router.post("/pilot-clear")
async def pilot_clear():
    """מנקה את לוג הפיילוט."""
    _wa_pilot_log.clear()
    return {"status": "cleared"}


@router.post("/bulk-reengagement")
async def bulk_reengagement(request: Request):
    """שולח re-engagement לרשימת לידים — מקסימום 100."""
    data = await request.json()
    leads = data.get("leads", [])[:100]
    results = []
    for lead in leads:
        phone = str(lead.get("phone", "")).strip()
        name = lead.get("name", "") or None
        project_name = lead.get("project_name", "") or ""
        agent_name = lead.get("agent_name", "") or ""
        if not phone:
            results.append({"phone": phone, "status": "skipped", "reason": "no_phone"})
            continue
        try:
            start_reengagement(phone, name, project_name, agent_name)
            results.append({"phone": phone, "status": "sent"})
        except Exception as e:
            results.append({"phone": phone, "status": "error", "reason": str(e)})
        time.sleep(2)
    sent = sum(1 for r in results if r["status"] == "sent")
    failed = sum(1 for r in results if r["status"] == "error")
    return {"sent": sent, "failed": failed, "results": results}


@router.post("/start-reengagement")
async def start_reengagement_endpoint(request: Request):
    """מפעיל start_reengagement מרחוק — לבדיקות ולשליחה ידנית."""
    data = await request.json()
    phone = str(data.get("phone", ""))
    name = data.get("name")
    project_name = data.get("project_name", "")
    agent_name = data.get("agent_name", "")
    start_reengagement(phone, name, project_name, agent_name)
    return {"status": "sent", "phone": phone}


@router.post("/reset-session")
async def reset_session(request: Request):
    """מאפס session של טלפון — לבדיקות."""
    data = await request.json()
    phone = str(data.get("phone", "")).replace("+", "").replace(" ", "")
    _wa_sessions.pop(phone, None)
    _wa_done.discard(phone)
    _wa_seen_sids.clear()
    return {"status": "reset", "phone": phone}


if __name__ == "__main__":
    send_test()
