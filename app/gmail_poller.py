"""Gmail IMAP — סריקת תיבת דואר נכנס ותגובה אוטומטית."""

import os
import imaplib
import email
from email.header import decode_header
import re

GMAIL_USER = os.getenv("GMAIL_USER", "orencohengroup2020@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
BOT_EMAIL = os.getenv("BOT_EMAIL", "daniel@orencohengroup.com")

_processed_ids: set = set()


def _decode_str(s) -> str:
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="ignore")
    return s or ""


def _get_text(msg) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                if payload:
                    text += payload.decode("utf-8", errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode("utf-8", errors="ignore")
    return text


def poll_inbox():
    """סורק מיילים חדשים ב-Gmail ועונה עליהם."""
    from .engine import Conversation
    from . import database as db
    from .email_api import _send_email, _email_sessions

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD.replace(" ", ""))
        mail.select("inbox")
        _, data = mail.search(None, "UNSEEN")
        mail_ids = data[0].split()
    except Exception as e:
        print(f"[GMAIL POLL ERROR] {e}")
        return

    for num in mail_ids:
        msg_id_str = num.decode()
        if msg_id_str in _processed_ids:
            continue
        _processed_ids.add(msg_id_str)

        try:
            _, msg_data = mail.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
        except Exception as e:
            print(f"[GMAIL FETCH ERROR] {e}")
            continue

        # שולח
        from_header = msg.get("From", "")
        from_email = ""
        if "<" in from_header:
            from_email = from_header.split("<")[1].rstrip(">").strip().lower()
        else:
            from_email = from_header.strip().lower()

        subject_raw = msg.get("Subject", "")
        subject_parts = decode_header(subject_raw)
        subject = ""
        for part, enc in subject_parts:
            if isinstance(part, bytes):
                subject += part.decode(enc or "utf-8", errors="ignore")
            else:
                subject += part

        internet_msg_id = msg.get("Message-ID", "")

        # סינון מיילים מהבוט עצמו ומיילים אוטומטיים
        skip_domains = ["noreply", "no-reply", "youtube.com", "gmail.com", "google.com", "linkedin.com", "facebook.com"]
        if not from_email or from_email == GMAIL_USER.lower() or from_email == BOT_EMAIL.lower() or any(s in from_email for s in skip_domains):
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        # בדוק שיש רשומה ב-DB עבור המייל הזה
        record = db.get_reengagement_record(f"email:{from_email}")
        if not record:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        # חילוץ טקסט
        text = _get_text(msg)

        # הסרת HTML
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # חיתוך quote
        cut_markers = [
            "מאת:", "From:", "-----Original", "________________________________",
            "wrote:", "כתב:", "נשלח:", "Sent:",
            "orencohengroup2020@gmail.com", "daniel@orencohengroup.com",
        ]
        earliest = len(text)
        for marker in cut_markers:
            idx = text.find(marker)
            if 0 < idx < earliest:
                earliest = idx
        if earliest > 5:
            text = text[:earliest].strip()

        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        print(f"[GMAIL INBOUND] from={from_email} subject={subject}")

        # שחזור session
        if from_email not in _email_sessions:
            lang = "he" if any('\u05d0' <= c <= '\u05ea' for c in (record.get('client_name') or '')) else "he"
            convo = Conversation(language=lang)
            if record and record.get("transcript"):
                for line in record["transcript"].split("\n"):
                    line = line.strip()
                    if line.startswith("Daniel:"):
                        convo.messages.append({"role": "assistant", "content": line[7:].strip()})
                    elif line.startswith("Client:"):
                        convo.messages.append({"role": "user", "content": line[7:].strip()})
            name = (record.get("client_name") or "") if record else ""
            convo.messages.append({
                "role": "user",
                "content": f"[הקשר: הלקוח {name} קיבל מייל פתיחה מדניאל ועונה שזה רלוונטי. שאל אותו רק שאלה 1: מהו לוח הזמנים שלך לכניסה לנכס? אל תשאל שאלות אחרות. תגובתו: '{text}']"
            })
            _email_sessions[from_email] = convo
            turn, score = convo.send(text)
        else:
            convo = _email_sessions[from_email]
            turn, score = convo.send(text)

        # עדכון תמליל
        record = db.get_reengagement_record(f"email:{from_email}")
        existing = (record.get("transcript") or "") if record else ""
        updated = existing + f"\nClient: {text}\nDaniel: {turn.reply}"
        db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())

        # שליחת תשובה
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
        html = f"<p>{turn.reply.replace(chr(10), '<br>')}</p>"
        try:
            _send_email(from_email, name if 'name' in dir() else "", reply_subject, html, turn.reply, internet_msg_id or None)
            print(f"[GMAIL REPLY] to={from_email}")
        except Exception as e:
            print(f"[GMAIL REPLY ERROR] {e}")

        mail.store(num, "+FLAGS", "\\Seen")

        if turn.handoff_to_human:
            _email_sessions.pop(from_email, None)
            print(f"[GMAIL HANDOFF] {from_email}")

    mail.logout()
