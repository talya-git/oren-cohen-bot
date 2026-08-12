"""Email reengagement — שליחה וקבלת מיילים דרך Mailjet."""

import os
import json
import urllib.request
import urllib.error
from fastapi import APIRouter, Request
from . import database as db

router = APIRouter(prefix="/api/email", tags=["email"])

BOT_EMAIL = os.getenv("BOT_EMAIL", "daniel@orencohengroup.com")
BOT_NAME = "Daniel | Oren Cohen Group"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

_email_sessions: dict = {}  # email -> conversation


def _send_email(to_email: str, to_name: str, subject: str, html: str, text: str, reply_to_msg_id: str | None = None) -> dict:
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from": {"email": BOT_EMAIL, "name": BOT_NAME},
        "reply_to": {"email": BOT_EMAIL, "name": BOT_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ]
    }
    if reply_to_msg_id:
        payload["headers"] = {
            "In-Reply-To": reply_to_msg_id,
            "References": reply_to_msg_id,
        }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            msg_id = resp.headers.get("X-Message-Id", "")
            print(f"[SENDGRID MSG-ID] {msg_id}")
            return {"status": resp.status, "message_id": msg_id}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[EMAIL ERROR] {e.code}: {body}")
        raise


def _build_greeting(name: str | None) -> str:
    greeting = f"Hi{' ' + name if name else ''},\n\n"
    greeting += (
        "This is Daniel from the Oren Cohen Group Real Estate office in Jerusalem.\n\n"
        "I'm reaching out as I saw that you had previously inquired about a property in Jerusalem. "
        "We currently have several exciting new developments and properties available, "
        "and I wanted to see whether buying in Jerusalem is still relevant for you.\n\n"
        "If so, I'd be happy to send you some options and see what might suit your requirements.\n\n"
        "Best regards,\nDaniel\nOren Cohen Group"
    )
    return greeting


@router.post("/start-reengagement")
async def start_email_reengagement(request: Request):
    from .engine import Conversation
    data = await request.json()
    email = str(data.get("email", "")).strip()
    name = data.get("name") or None
    project_name = data.get("project_name", "") or ""
    agent_email = data.get("agent_email", "") or ""
    custom_subject = data.get("custom_subject") or None
    custom_message = data.get("custom_message") or None

    if not email:
        return {"status": "error", "reason": "email required"}

    # בדיקת כפילות
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM reengagement_sent WHERE phone={db.PH} LIMIT 1", (f"email:{email}",))
    exists = db._fetchone(cur) is not None
    conn.close()
    if exists:
        return {"status": "duplicate"}

    greeting = custom_message or _build_greeting(name)
    subject = custom_subject or "Jerusalem Real Estate — New Opportunities"

    html = greeting.replace("\n", "<br>")
    try:
        _send_email(email, name or "", subject, f"<p>{html}</p>", greeting)
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    # שמירה ב-DB עם prefix email:
    db.mark_reengagement_sent(
        phone=f"email:{email}",
        client_name=name or "",
        agent_email=agent_email,
        transcript=f"Daniel: {greeting}"
    )

    # פתיחת session
    convo = Conversation(language="en", project_name=project_name or None)
    if name:
        convo.profile.contact_name = name
    convo.messages.append({"role": "assistant", "content": greeting})
    _email_sessions[email] = convo

    print(f"[EMAIL SENT] {email} | {name} | {project_name}")
    return {"status": "sent", "email": email}


@router.post("/inbound")
async def email_inbound(request: Request):
    """Mailjet Inbound Parse webhook — מקבל מיילים נכנסים."""
    from .engine import Conversation

    try:
        body = await request.json()
    except Exception:
        form = await request.form()
        body = dict(form)

    # Mailjet שולח מערך של הודעות
    messages = body if isinstance(body, list) else [body]

    for msg in messages:
        sender = msg.get("Sender") or msg.get("From") or ""
        # חילוץ כתובת מייל מהשדה
        if "<" in sender:
            email = sender.split("<")[1].rstrip(">").strip()
        else:
            email = sender.strip()

        text = msg.get("Text-part") or msg.get("stripped-text") or msg.get("TextPart") or ""
        text = text.strip()

        if not email or not text:
            continue

        print(f"[EMAIL INBOUND] from={email} text={text[:100]}")

        # שחזור session אם צריך
        if email not in _email_sessions:
            record = db.get_reengagement_record(f"email:{email}")
            convo = Conversation(language="en")
            if record and record.get("transcript"):
                for line in record["transcript"].split("\n"):
                    line = line.strip()
                    if line.startswith("Daniel:"):
                        convo.messages.append({"role": "assistant", "content": line[7:].strip()})
                    elif line.startswith("Client:"):
                        convo.messages.append({"role": "user", "content": line[7:].strip()})
            _email_sessions[email] = convo

        convo = _email_sessions[email]
        turn, score = convo.send(text)

        # עדכון תמליל
        record = db.get_reengagement_record(f"email:{email}")
        existing = (record.get("transcript") or "") if record else ""
        updated = existing + f"\nClient: {text}\nDaniel: {turn.reply}"
        db.update_reengagement_replied(f"email:{email}", True, updated.strip())

        # שליחת תשובה
        subject = "Re: Jerusalem Real Estate — New Opportunities"
        html = turn.reply.replace("\n", "<br>")
        try:
            _send_email(email, convo.profile.contact_name or "", subject, f"<p>{html}</p>", turn.reply)
        except Exception as e:
            print(f"[EMAIL REPLY ERROR] {e}")

        if turn.handoff_to_human:
            _email_sessions.pop(email, None)
            print(f"[EMAIL HANDOFF] {email}")

    return {"status": "ok"}


@router.delete("/clear-test")
async def clear_test_email(email: str):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM reengagement_sent WHERE phone={db.PH}", (f"email:{email}",))
    conn.commit()
    conn.close()
    return {"status": "deleted", "email": email}


@router.get("/sent")
async def email_sent():
    """מחזיר את כל השיחות במייל."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM reengagement_sent
        WHERE phone LIKE 'email:%'
        ORDER BY sent_at DESC
    """)
    rows = db._fetchall(cur)
    conn.close()
    return {"conversations": rows}
