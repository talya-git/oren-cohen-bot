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
    # מספרים אמריקאים - שימוש בתבנית utility
    if normalized.startswith("1") and len(normalized) == 11:
        template_name = "reengagement_en_utility"
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
        raise Exception("DUPLICATE")
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
            f"This is Daniel from the Oren Cohen Group Real Estate office in Jerusalem.\n\n"
            f"I'm reaching out as I saw that you had previously inquired about a property in Jerusalem. "
            f"We currently have several exciting new developments and properties available, "
            f"and I wanted to see whether buying in Jerusalem is still relevant for you.\n\n"
            f"If so, I'd be happy to send you some options and see what might suit your requirements."
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



_NOT_RELEVANT = ["לא רלוונטי", "לא מעוניין", "לא רלוונט", "לא מתעניין", "לא צריך", "לא רוצה", "not relevant", "not interested", "הסר", "remove", "unsubscribe", "stop", "אין צורך", "לא רלוונטי לי", "לא רלוונט לי", "לא רלוונטי עבורי", "לא רלוונט עבורי", "לא רלוונטי עבורנו", "no thanks", "no thank you", "not for me", "לא תודה", "לא, תודה", "תודה לא", "לא מעניין", "לא רלוונטי כרגע", "לא עכשיו תודה"]
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
            elif status == "failed" and recipient:
                from . import database as _db
                conn = _db.get_db()
                cur = conn.cursor()
                cur.execute(f"DELETE FROM reengagement_sent WHERE phone={_db.PH}", (f"+{recipient}",))
                conn.commit()
                conn.close()
                print(f"[FAILED-DELETED] {recipient}")
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

    # זיהוי הודעות אוטומטיות מעסקים
    _AUTO_REPLY_SIGNALS = [
        "received your message", "we'll get back", "will get back",
        "קבלנו הודעתכם", "נחזור אליכם", "whatsapp.com/channel",
        "https://", "automated", "auto-reply", "out of office",
    ]
    if len(text) > 200 or any(s in text.lower() for s in _AUTO_REPLY_SIGNALS):
        print(f"[AUTO-REPLY IGNORED] {phone}: {text[:80]}...")
        return {"status": "auto_reply_ignored"}
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
        print(f"[DONE_REPLY] phone={phone} reply={reply!r}")
        send_message(f"+{phone}", reply)
        # שמירת ההמשך ב-DB
        existing = _db.get_reengagement_record(f"+{phone}")
        if existing:
            old = existing.get("transcript") or ""
            _db.update_reengagement_replied(f"+{phone}", True, old + f"\nלקוח: {text}\nדניאל: {reply}")
        return {"status": "done_reply"}

    if phone not in _wa_sessions:
        intent = _classify_response(text)
        if intent == "not_relevant":
            _save_followup(phone, weeks=26, reason="not_relevant")
            msg_lower = text.lower()
            if "הסר" in msg_lower or "remove" in msg_lower or "unsubscribe" in msg_lower or "stop" in msg_lower:
                reply_msg = "אוקי, סליחה על ההטרדה! נשמח לעזור לך תמיד אם תצטרך 😊"
            else:
                reply_msg = "מובן, תודה על התשובה! אם בעתיד תתעניין — אנחנו כאן 😊"
            send_message(f"+{phone}", reply_msg)
            _db.update_reengagement_replied(f"+{phone}", True, f"לקוח: {text}\nדניאל: {reply_msg}")
            dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
            try:
                sehel.log_call_summary(f"+{phone}", f"בוט וואטסאפ: לקוח ענה 'לא רלוונטי' ({text})", dry_run=dry)
            except Exception as e:
                print(f"[SEHEL CALL LOG ERROR] {e}")
            return {"status": "snoozed_26w"}
        if intent == "snooze_week":
            _save_followup(phone, weeks=1, reason="snooze")
            reply_msg = "בטח, אחזור אליך בשבוע הבא! 😊"
            send_message(f"+{phone}", reply_msg)
            _db.update_reengagement_replied(f"+{phone}", True, f"לקוח: {text}\nדניאל: {reply_msg}")
            dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
            try:
                sehel.log_call_summary(f"+{phone}", f"בוט וואטסאפ: לקוח ענה 'לא עכשיו' ({text})", dry_run=dry)
            except Exception as e:
                print(f"[SEHEL CALL LOG ERROR] {e}")
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
            # הוסף הקשר לבוט שמסביר את המצב
            conv.messages.append({
                "role": "user",
                "content": f"[הקשר: הלקוח קיבל הודעת וואטסאפ מדניאל ועונה. אם הלקוח שואל 'מי זה' — הסבר בקצרה שאתה דניאל מאורן כהן גרופ ושלחת לו הודעה. תגובתו: '{text}']"
            })
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
        # נקה backticks ו-JSON
        import re as _re
        content = _re.sub(r'```(?:json)?', '', content).strip()
        if content.startswith('{'):
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
        if score.level in ("High", "Medium"):
            _db.mark_reengagement_handoff(f"+{phone}")
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
            payload["tags[]"] = payload.get("tags[]", []) + ["בוט"]
            sehel.push_lead(payload, dry_run=dry)
            transcript_text = "\n".join(
                f"{'\u05d3\u05e0\u05d9\u05d0\u05dc' if m['role']=='assistant' else '\u05dc\u05e7\u05d5\u05d7'}: {m['content']}"
                for m in convo.messages if m.get('role') in ('assistant','user')
            )
            sehel.log_call_summary(
                convo.profile.phone,
                f"בוט וואטסאפ — שיחה הושלמה, ליד {score.level}:\n{transcript_text}",
                dry_run=dry
            )
        except Exception as e:
            print(f"[SEHEL ERROR] {e}")

        try:
            from .mailer import send_hot_lead_alert
            send_hot_lead_alert(
                name=convo.profile.contact_name or phone,
                phone=f"+{phone}",
                score=score.level,
                transcript=transcript_text,
            )
        except Exception as e:
            print(f"[HOT LEAD ALERT ERROR] {e}")
        del _wa_sessions[phone]

    return {"status": "ok"}


@router.post("/send-message")
async def send_free_message(request: Request):
    from . import database as _db
    data = await request.json()
    phone = str(data.get("phone", "")).strip()
    message = str(data.get("message", "")).strip()
    if not phone or not message:
        return {"status": "error", "reason": "phone and message required"}
    result = send_message(phone, message)
    # עדכון התמליל ב-DB
    record = _db.get_reengagement_record(phone)
    if record:
        existing = record.get("transcript") or ""
        updated = existing + f"\nדניאל: {message}"
        _db.update_reengagement_replied(phone, bool(record.get("replied")), updated.strip())
    return {"status": "sent", "result": result}


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
    cur.execute(f"SELECT phone, sent_at FROM reengagement_sent WHERE LOWER(agent_email)=LOWER({_db.PH})", (agent_email,))
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
               rs.handoff
        FROM reengagement_sent rs
        LEFT JOIN reengagement_batches rb ON rs.batch_id = rb.id
        WHERE rs.phone NOT LIKE 'email:%'
        ORDER BY rs.sent_at DESC
    """)
    rows = _db._fetchall(cur)
    conn.close()

    # מיפוי מייל לשם סוכן
    email_to_label = {
        'yaniv@orencohengroup.com': 'יניב',
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
        'nethanele@orencohengroup.com': 'נתנאל',
    }

    def _str(v):
        if v is None:
            return ''
        if hasattr(v, 'isoformat'):
            return v.isoformat()
        return str(v) if v else ''

    conversations = []
    for r in rows:
        label = r.get('agent_label') or email_to_label.get((r.get('agent_email') or '').lower(), r.get('agent_email',''))
        transcript = r['transcript'] or ''
        # תקן Daniel: -> דניאל: בתמליל
        transcript = transcript.replace('Daniel: ', 'דניאל: ').replace('Daniel:', 'דניאל:')
        conversations.append({
            'phone': r['phone'] or '',
            'client_name': _str(r.get('client_name')),
            'agent_label': label or '',
            'replied': bool(r['replied']),
            'handoff': bool(r['handoff']),
            'transcript': transcript,
            'sent_at': _str(r.get('sent_at')),
            'project_name': '',
            'error': _str(r.get('error')),
            'read_at': _str(r.get('read_at')),
        })
    from fastapi.responses import Response
    import json as _json
    from datetime import datetime, date

    class _DTEncoder(_json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            return super().default(o)

    return Response(
        content=_json.dumps({"conversations": conversations}, cls=_DTEncoder, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
    )


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
        status = "duplicate" if "DUPLICATE" in str(e) else "error"
        reason = str(e)
    try:
        from .mailer import send_bulk_report
        label = agent_name or agent_email or name or phone
        send_bulk_report(label, [{"phone": phone, "status": status, "reason": reason}], agent_email=agent_email)
    except Exception as e:
        print(f"[ADMIN REPORT ERROR] {e}")
    if status == "duplicate":
        return {"status": "duplicate", "phone": phone, "reason": "already sent"}
    if status == "error":
        return {"status": "error", "phone": phone, "reason": reason}
    return {"status": "sent", "phone": phone}


@router.post("/fix-false-handoffs")
async def fix_false_handoffs():
    """מתקן handoff שגויים — מסיר handoff מלידים שענו שלילי."""
    from . import database as _db
    negative_keywords = [
        "לא רלוונט", "לא מעוניין", "לא צריך", "לא רוצה", "אין צורך",
        "לא מתעניין", "not relevant", "not interested", "no thanks", "no thank you",
        "מובן, תודה", "אנחנו כאן", "אנחנו כאן 😊",
        "לא תודה", "לא, תודה", "תודה לא", "לא מעניין"
    ]
    conn = _db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT phone, transcript FROM reengagement_sent WHERE handoff=TRUE")
    rows = _db._fetchall(cur)
    fixed = 0
    for r in rows:
        transcript = (r.get("transcript") or "").lower()
        if any(kw.lower() in transcript for kw in negative_keywords):
            cur.execute(
                f"UPDATE reengagement_sent SET handoff={_db.PH} WHERE phone={_db.PH}",
                (False if _db.DATABASE_URL else 0, r["phone"])
            )
            fixed += 1
    conn.commit()
    conn.close()
    print(f"[FIX-HANDOFFS] fixed {fixed} records")
    return {"fixed": fixed}


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
