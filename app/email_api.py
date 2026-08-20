"""Email reengagement — שליחה וקבלת מיילים דרך Gmail SMTP."""

import os
from fastapi import APIRouter, Request
from . import database as db

router = APIRouter(prefix="/api/email", tags=["email"])

BOT_EMAIL = os.getenv("BOT_EMAIL", "daniel@orencohengroup.com")
BOT_NAME = "Daniel | Oren Cohen Group"
GMAIL_USER = os.getenv("GMAIL_USER", "orencohengroup2020@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

_email_sessions: dict = {}


def _send_email(to_email: str, to_name: str, subject: str, html: str, text: str, reply_to_msg_id: str | None = None) -> dict:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((BOT_NAME, GMAIL_USER))
    msg["To"] = to_email
    msg["Reply-To"] = GMAIL_USER
    if reply_to_msg_id:
        msg["In-Reply-To"] = reply_to_msg_id
        msg["References"] = reply_to_msg_id

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD.replace(" ", ""))
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
    return {"status": "sent"}


BOAZ_EMAIL = "tsalyato@orencohengroup.com"


def _send_agent_alert(agent_email: str, client_name: str, phone_or_email: str, transcript: str, channel: str = "WhatsApp") -> None:
    recipients = [agent_email]
    if agent_email.lower() != BOAZ_EMAIL:
        recipients.append(BOAZ_EMAIL)

    # פירמוט תמליל עם שורות נפרדות
    formatted = transcript.replace('\n', '<br>').replace('דניאל:', '<br><b>דניאל:</b>').replace('לקוח:', '<br><b>לקוח:</b>').replace('Daniel:', '<br><b>Daniel:</b>').replace('Client:', '<br><b>Client:</b>')

    subject = f"🔔 ליד מתעניין ({channel}) — {client_name or phone_or_email}"
    html = (
        f"<div dir='rtl' style='font-family:Arial,sans-serif;font-size:14px;line-height:1.6'>"
        f"<h2 style='color:#16a34a;'>🔔 ליד מתעניין מהבוט!</h2>"
        f"<p><b>שם:</b> {client_name or '—'}</p>"
        f"<p><b>{'טלפון' if channel == 'WhatsApp' else 'מייל'}:</b> {phone_or_email}</p>"
        f"<p><b>ערוץ:</b> {channel}</p>"
        f"<hr style='border:none;border-top:1px solid #e2e8f0;margin:12px 0'>"
        f"<h4 style='margin-bottom:8px'>תמליל שיחה:</h4>"
        f"<div style='background:#f8f9fa;padding:14px;border-radius:8px;font-size:13px;direction:rtl;line-height:1.8'>{formatted}</div>"
        f"</div>"
    )
    text_body = f"ליד מתעניין: {client_name or phone_or_email}\n{phone_or_email}\n\n{transcript}"
    for to in recipients:
        try:
            _send_email(to, "", subject, html, text_body)
            print(f"[AGENT ALERT] sent to {to}")
        except Exception as e:
            print(f"[AGENT ALERT ERROR] {to}: {e}")


def _build_greeting(name: str | None) -> str:
    is_hebrew = name and any('\u05d0' <= c <= '\u05ea' for c in name)
    if is_hebrew or not name:
        greeting = f"היי{' ' + name if name else ''},\n\n"
        greeting += (
            "כאן דניאל מאורן כהן גרופ בירושלים.\n"
            "אני פונה אליך בהמשך לפנייתך למשרדנו בעבר.\n\n"
            "בימים אלו אנחנו מרכזים עבור לקוחותינו מספר הזדמנויות נדל\"ן מיוחדות בפרויקטים עתידיים בירושלים.\n\n"
            "האם הנושא עדיין רלוונטי עבורך?\n\n"
            "בברכה,\nדניאל\nאורן כהן גרופ"
        )
    else:
        greeting = f"Hi {name},\n\n"
        greeting += (
            "This is Daniel from Oren Cohen Group in Jerusalem.\n"
            "I'm reaching out as a follow-up to your previous inquiry with our office.\n\n"
            "We are currently curating exclusive real estate opportunities in upcoming Jerusalem projects for our clients.\n\n"
            "Is this still of interest to you?\n\n"
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

    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM reengagement_sent WHERE phone={db.PH} LIMIT 1", (f"email:{email}",))
    exists = db._fetchone(cur) is not None
    conn.close()
    if exists:
        return {"status": "duplicate"}

    is_hebrew = name and any('\u05d0' <= c <= '\u05ea' for c in name)
    lang = "he" if (is_hebrew or not name) else "en"
    greeting = custom_message or _build_greeting(name)
    subject = custom_subject or ("הזדמנויות נדל\"ן בירושלים — אורן כהן גרופ" if lang == "he" else "Real Estate Opportunities in Jerusalem — Oren Cohen Group")
    html = greeting.replace("\n", "<br>")

    try:
        _send_email(email, name or "", subject, f'<div dir="rtl" style="text-align:right">{html}</div>', greeting)
        print(f"[EMAIL SENT] {email} | {name} | {project_name}")
    except Exception as e:
        print(f"[EMAIL SEND FAILED] {e}")
        return {"status": "error", "reason": str(e)}

    db.mark_reengagement_sent(
        phone=f"email:{email}",
        client_name=name or "",
        agent_email=agent_email,
        transcript=f"Daniel: {greeting}"
    )

    convo = Conversation(language="he", project_name=project_name or None)
    if name:
        convo.profile.contact_name = name
    convo.messages.append({"role": "assistant", "content": greeting})
    _email_sessions[email] = convo

    return {"status": "sent", "email": email}


@router.get("/clear-test")
@router.delete("/clear-test")
async def clear_test_email(email: str):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM reengagement_sent WHERE phone={db.PH}", (f"email:{email}",))
    conn.commit()
    conn.close()
    return {"status": "deleted", "email": email}


@router.post("/fix-transcript")
async def fix_transcript(request: Request):
    data = await request.json()
    email = data.get("email", "").strip()
    transcript = data.get("transcript", "").strip()
    if not email or not transcript:
        return {"status": "error", "reason": "email and transcript required"}
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"UPDATE reengagement_sent SET transcript={db.PH} WHERE phone={db.PH}", (transcript, f"email:{email}"))
    conn.commit()
    conn.close()
    return {"status": "updated", "email": email}


@router.get("/sent")
async def email_sent():
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
