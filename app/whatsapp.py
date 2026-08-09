"""שליחת הודעות WhatsApp דרך Meta Cloud API."""

import asyncio
import os
import time
import requests

from . import sehel

META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "1285155738009042")
META_API_VERSION = "v19.0"

NO_RESPONSE_HOURS = 24


def _token() -> str:
    return os.getenv("META_ACCESS_TOKEN", "")


def send_message(phone: str, message: str) -> dict:
    normalized = phone.lstrip("+").replace(" ", "").replace("-", "")
    resp = requests.post(
        f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": normalized,
            "type": "text",
            "text": {"body": message}
        },
        timeout=15,
    )
    result = resp.json()
    print(f"[META SEND] phone={normalized} status={resp.status_code} result={result}")
    return result


def send_template_reengagement(phone: str, name: str | None, lang: str = "he") -> dict:
    """שולח template reengagement — עובד גם אחרי 24 שעות."""
    normalized = phone.lstrip("+").replace(" ", "").replace("-", "")
    components = []
    if name:
        components = [{"type": "body", "parameters": [{"type": "text", "text": name}]}]
    template_name = "reengagement_he" if lang == "he" else "reengagement_en"
    lang_code = "he" if lang == "he" else "en"
    resp = requests.post(
        f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": normalized,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang_code},
                "components": components,
            },
        },
        timeout=15,
    )
    result = resp.json()
    print(f"[META TEMPLATE] phone={normalized} lang={lang} status={resp.status_code} result={result}")
    return result


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
_wa_pilot_log: list[dict] = []


def _detect_language(phone: str, name: str | None) -> str:
    normalized = phone.lstrip("+")
    is_israeli = normalized.startswith("972") or normalized.startswith("05")
    if is_israeli:
        if name and any("a" <= c.lower() <= "z" for c in name):
            return "en"
        return "he"
    return "en"


def _check_whatsapp_allowed(normalized: str) -> str:
    return "allow"


def _has_whatsapp(phone_e164: str) -> bool:
    return True


def start_reengagement(phone: str, name: str | None, project_name: str, agent_name: str = "", agent_email: str = "") -> None:
    """שולח הודעת פתיחה ללקוח ישן ומאתחל session."""
    from .engine import Conversation

    normalized = phone.lstrip("+")
    if normalized.startswith("05"):
        normalized = "972" + normalized[1:]
    elif normalized.startswith("5") and len(normalized) == 9:
        normalized = "972" + normalized
    # מספר אמריקאי ללא קידומת מדינה (10 ספרות, מתחיל בקידומת אזורית)
    elif len(normalized) == 10 and normalized[0] in "23456789" and not normalized.startswith("972"):
        normalized = "1" + normalized

    from . import database as _db
    if _db.get_sent_phones_set(f"+{normalized}"):
        print(f"[SKIP DUPLICATE] {normalized} — כבר נשלח בעבר")
        return
    if name:
        try:
            fixed = name.encode("latin1").decode("utf-8")
            if any("\u05d0" <= c <= "\u05ea" for c in fixed):
                name = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    # אם השם עדיין מכיל תווים לא תקינים — נשמיט אותו
    if name and not any(c.isalpha() for c in name):
        name = None

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
    result = send_template_reengagement(f"+{normalized}", name, lang)
    if "error" in result or (result.get("messages", [{}])[0].get("message_status") == "failed"):
        error_msg = result.get("error", {}).get("message", "Meta API error")
        raise Exception(error_msg)

    from . import database as _db
    final_agent_email = agent_email or ("aaron@orencohengroup.com" if is_projects else "office@orencohengroup.com")
    initial_transcript = f"דניאל: {greeting}"
    _db.mark_reengagement_sent(f"+{normalized}", name or "", final_agent_email, transcript=initial_transcript)

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


@router.get("/webhook")
async def whatsapp_webhook_verify(request: Request):
    """Meta webhook verification."""
    params = request.query_params
    if params.get("hub.verify_token") == "oren_cohen_verify" and params.get("hub.challenge"):
        return int(params["hub.challenge"])
    return {"status": "invalid"}


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    from .engine import Conversation
    from . import database as _db

    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    print(f"[WEBHOOK] body={body}")

    # פורמט Meta Cloud API
    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]
        # טיפול בסטטוסים (sent/delivered/read/failed)
        if "statuses" in change and "messages" not in change:
            status_update = change["statuses"][0]
            status = status_update.get("status")
            recipient = status_update.get("recipient_id", "")
            if status == "read" and recipient:
                from . import database as _db
                conn = _db.get_db()
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE reengagement_sent SET read_at=NOW() WHERE phone={_db.PH} AND read_at IS NULL",
                    (f"+{recipient}",)
                )
                conn.commit()
                conn.close()
                print(f"[READ] {recipient}")
            return {"status": "status_update"}
        msg = change["messages"][0]
        phone = msg["from"]
        text = msg["text"]["body"].strip()
        msg_sid = msg["id"]
    except (KeyError, IndexError):
        return {"status": "ignored"}

    if msg_sid and msg_sid in _wa_seen_sids:
        return {"status": "duplicate"}
    if msg_sid:
        _wa_seen_sids.add(msg_sid)

    if not phone or not text:
        return {"status": "ignored"}

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

        # שחזור session מה-DB אם השרת נרדם
        db_record = _db.get_reengagement_record(f"+{phone}")
        conv = Conversation()
        if db_record and db_record.get("transcript"):
            # שחזור ההיסטוריה מהתמליל
            for line in db_record["transcript"].split("\n"):
                line = line.strip()
                if line.startswith("דניאל:") or line.startswith("Daniel:"):
                    conv.messages.append({"role": "assistant", "content": line.split(":", 1)[1].strip()})
                elif line.startswith("לקוח:") or line.startswith("Client:"):
                    conv.messages.append({"role": "user", "content": line.split(":", 1)[1].strip()})
            if db_record.get("client_name"):
                conv.profile.contact_name = db_record["client_name"]
            conv.profile.phone = f"+{phone}"
            print(f"[SESSION RESTORED] {phone} — {len(conv.messages)} הודעות")
        else:
            conv.messages.append({
                "role": "user",
                "content": f"[הקשר: הלקוח קיבל הודעת פתיחה מדניאל ועונה שהוא מעוניין. תגובתו: '{text}'. אל תאמר 'שלום וברכה'. שאל ישירות את שאלה מספר 1: לוח הזמנים לכניסה לנכס.]"
            })
        _wa_sessions[phone] = conv

    convo = _wa_sessions[phone]
    turn, score = convo.send(text)

    log_entry = next((e for e in _wa_pilot_log if e["phone"] == f"+{phone}"), None)
    if log_entry:
        log_entry["replied"] = True
        if turn.handoff_to_human:
            log_entry["handoff"] = True
            log_entry["score"] = score.level
            log_entry["notes"] = turn.notes or ""

    import json as _json
    transcript_lines = []
    for m in convo.messages:
        if m.get('role') not in ('assistant', 'user'):
            continue
        content = m['content']
        if content.startswith('[') or content.startswith('{'):
            # נסה לפרסר JSON ולחלץ רק reply
            try:
                parsed = _json.loads(content)
                if isinstance(parsed, dict):
                    content = parsed.get('reply', '')
                else:
                    continue
            except Exception:
                continue
        if not content or content.startswith('['):
            continue
        role_label = 'דניאל' if m['role'] == 'assistant' else 'לקוח'
        transcript_lines.append(f"{role_label}: {content}")
    transcript_text = "\n".join(transcript_lines)
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
    from . import database as _db
    data = await request.json()
    agent_email = data.get("agent_email", "")
    agent_label = data.get("agent_label", "")
    phones = data.get("phones", [])

    if not agent_email:
        return {"status": "error", "reason": "no agent_email"}

    batch_id = _db.create_reengagement_batch(agent_email, agent_label)

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
    conn = _db.get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT phone, sent_at FROM reengagement_sent WHERE agent_email={_db.PH}", (agent_email,))
    rows = _db._fetchall(cur)
    conn.close()
    phones = [r["phone"] for r in rows]
    phones_with_dates = [{"phone": r["phone"], "sent_at": r["sent_at"]} for r in rows]
    return {"phones": phones, "phones_with_dates": phones_with_dates}


@router.get("/reengagement-results")
async def reengagement_results(agent_email: str):
    from . import database as _db
    return {"results": _db.get_reengagement_results(agent_email)}


@router.get("/conversations/all")
async def all_conversations():
    """מחזיר את כל השיחות עם תמליל לדף הניהול."""
    from . import database as _db
    conn = _db.get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT rs.phone, rs.client_name, rs.agent_email, rs.replied, rs.transcript, rs.sent_at,
               rs.read_at,
               rb.agent_label,
               CASE WHEN rs.transcript LIKE '%יום טוב%' OR rs.transcript LIKE '%להתראות%'
                    OR rs.transcript LIKE '%bye%' OR rs.transcript LIKE '%thank you%'
                    THEN true ELSE false END as handoff
        FROM reengagement_sent rs
        LEFT JOIN reengagement_batches rb ON rs.batch_id = rb.id
        ORDER BY rs.sent_at DESC
    """)
    rows = _db._fetchall(cur)
    conn.close()

    # מיפוי מייל לשם סוכן
    email_to_label = {
        'yaniv@orencohengroup.com': 'ינון',
        'moshe@orencohengroup.com': 'משה',
        'miri@orencohengroup.com': 'מירי',
        'michael@orencohengroup.com': 'מיכאל',
        'rivka@orencohengroup.com': 'רבקה',
        'uriel400@orencohengroup.com': 'אוריאל',
        'elchanan@orencohengroup.com': 'אלחנן',
        'oren@orencohengroup.com': 'אורן',
        'aryeh@orencohengroup.com': 'אריה',
        'office@orencohengroup.com': 'בועז',
        'hannah@orencohengroup.com': 'חנה',
        'aaron@orencohengroup.com': 'אהרון',
        'lisa@orencohengroup.com': 'ליסה',
        'dovr@orencohengroup.com': 'דב',
    }

    conversations = []
    for r in rows:
        label = r.get('agent_label') or email_to_label.get(r.get('agent_email',''), r.get('agent_email',''))
        conversations.append({
            'phone': r['phone'],
            'client_name': r['client_name'],
            'agent_label': label,
            'replied': bool(r['replied']),
            'handoff': bool(r['handoff']),
            'transcript': r['transcript'] or '',
            'sent_at': r['sent_at'],
            'project_name': '',
            'error': r.get('error') or '',
            'read_at': r.get('read_at') or '',
        })
    return {'conversations': conversations}


@router.get("/pilot-results")
async def pilot_results():
    return {"results": _wa_pilot_log}


@router.post("/pilot-clear")
async def pilot_clear():
    _wa_pilot_log.clear()
    return {"status": "cleared"}


@router.post("/bulk-reengagement")
async def bulk_reengagement(request: Request):
    data = await request.json()
    leads = data.get("leads", [])[:100]
    results = []
    for lead in leads:
        phone = str(lead.get("phone", "")).strip()
        name = lead.get("name", "") or None
        project_name = lead.get("project_name", "") or ""
        agent_name = lead.get("agent_name", "") or ""
        agent_email = lead.get("agent_email", "") or ""
        if not phone:
            results.append({"phone": phone, "status": "skipped", "reason": "no_phone"})
            continue
        try:
            start_reengagement(phone, name, project_name, agent_name, agent_email or "")
            results.append({"phone": phone, "status": "sent"})
        except Exception as e:
            # שמירת שיחות שנכשלו גם ב-DB
            from . import database as _db
            _db.mark_reengagement_sent(f"+{phone}", name or "", "", error=str(e))
            results.append({"phone": phone, "status": "error", "reason": str(e)})
        time.sleep(2)
    sent = sum(1 for r in results if r["status"] == "sent")
    failed = sum(1 for r in results if r["status"] == "error")
    try:
        from .mailer import send_bulk_report
        agent_label = leads[0].get("agent_name", "") or leads[0].get("agent_email", "") if leads else ""
        agent_email = leads[0].get("agent_email", "") if leads else ""
        send_bulk_report(agent_label or "לא ידוע", results, agent_email=agent_email or None)
    except Exception as e:
        print(f"[ADMIN REPORT ERROR] {e}")
    return {"sent": sent, "failed": failed, "results": results}


@router.post("/start-reengagement")
async def start_reengagement_endpoint(request: Request):
    data = await request.json()
    phone = str(data.get("phone", ""))
    name = data.get("name")
    project_name = data.get("project_name", "")
    agent_name = data.get("agent_name", "") or data.get("agent_label", "")
    agent_email = data.get("agent_email", "") or None
    try:
        start_reengagement(phone, name, project_name, agent_name, agent_email or "")
        status = "sent"
        reason = ""
    except Exception as e:
        status = "error"
        reason = str(e)
    try:
        from .mailer import send_bulk_report
        label = agent_name or agent_email or name or phone
        send_bulk_report(label, [{"phone": phone, "status": status, "reason": reason}], agent_email=agent_email)
    except Exception as e:
        print(f"[ADMIN REPORT ERROR] {e}")
    if status == "error":
        return {"status": "error", "phone": phone, "reason": reason}
    return {"status": "sent", "phone": phone}


@router.post("/reset-session")
async def reset_session(request: Request):
    data = await request.json()
    phone = str(data.get("phone", "")).replace("+", "").replace(" ", "")
    _wa_sessions.pop(phone, None)
    _wa_done.discard(phone)
    _wa_seen_sids.clear()
    # מחיקת הרשומה מה-DB כדי לאפשר שליחה מחדש
    from . import database as _db
    conn = _db.get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM reengagement_sent WHERE phone={_db.PH}", (f"+{phone}",))
    conn.commit()
    conn.close()
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "data" / "followups.json"
    if f.exists():
        records = json.loads(f.read_text(encoding="utf-8"))
        records = [r for r in records if r.get("phone", "").replace("+", "") != phone]
        f.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "reset", "phone": phone}
