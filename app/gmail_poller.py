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


def _build_convo_from_transcript(transcript: str, lang: str):
    """בונה Conversation עם היסטוריה מלאה מהטרנסקריפט."""
    from .engine import Conversation
    convo = Conversation(language=lang)
    for line in transcript.split("\n"):
        line = line.strip()
        if line.startswith("Daniel:"):
            convo.messages.append({"role": "assistant", "content": line[7:].strip()})
        elif line.startswith("Client:"):
            convo.messages.append({"role": "user", "content": line[7:].strip()})
    return convo


def poll_inbox():
    """סורק מיילים חדשים ב-Gmail ועונה עליהם."""
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

        # סינון
        skip_domains = ["noreply", "no-reply", "mailer-daemon", "sendgrid", "mailjet"]
        if not from_email or from_email == GMAIL_USER.lower() or from_email == BOT_EMAIL.lower() or any(s in from_email for s in skip_domains):
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        # בדוק שיש רשומה ב-DB
        record = db.get_reengagement_record(f"email:{from_email}")
        if not record:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        # חילוץ טקסט
        text = _get_text(msg)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # חיתוך quote
        cut_markers = ["מאת:", "From:", "-----Original", "________________________________",
                       "wrote:", "כתב:", "נשלח:", "Sent:",
                       "orencohengroup2020@gmail.com", "daniel@orencohengroup.com",
                       "On ", "> "]
        earliest = len(text)
        for marker in cut_markers:
            idx = text.find(marker)
            if 0 < idx < earliest:
                earliest = idx
        if earliest > 2:
            text = text[:earliest].strip()
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        print(f"[GMAIL INBOUND] from={from_email} subject={subject}")

        name = record.get("client_name") or ""
        lang = "he" if (not name or any('\u05d0' <= c <= '\u05ea' for c in name)) else "en"

        # בנה session חדש מהטרנסקריפט הנוכחי ב-DB (כולל כל ההיסטוריה)
        transcript = record.get("transcript") or ""

        # אם כבר היה handoff — לא לענות
        if record.get("handoff") or "[HANDOFF]" in transcript:
            mail.store(num, "+FLAGS", "\\Seen")
            print(f"[GMAIL SKIP] handoff already done for {from_email}")
            continue

        convo = _build_convo_from_transcript(transcript, lang)

        # אם אין היסטוריה — הלקוח עונה לראשונה
        if not convo.messages:
            convo.messages.append({"role": "assistant", "content": "האם הנושא עדיין רלוונטי עבורך?"})

        # שמור ב-sessions
        _email_sessions[from_email] = convo

        # זיהוי תשובה חיובית לשאלת הפתיחה
        positive_words = ["כן", "רלוונטי", "מעוניין", "מעוניינת", "אשמח", "בטח", "כמובן", "yes", "interested", "sure", "absolutely"]
        is_first_reply = len([m for m in convo.messages if m["role"] == "user"]) == 0
        is_positive = any(w in text.lower() for w in positive_words)

        if is_first_reply and is_positive:
            actual_text = f"[הלקוח ענה חיובית: '{text}'. שאל אותו עכשיו רק שאלה 1: מהו לוח הזמנים שלך לכניסה לנכס? אל תשאל על מחיר, דרישות או כל דבר אחר.]"
        else:
            actual_text = text

        # שלח את ההודעה לבוט
        turn, score = convo.send(actual_text)

        # עדכון תמליל ב-DB
        updated = transcript + f"\nClient: {text}\nDaniel: {turn.reply}"
        db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())

        # שליחת תשובה
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
        html = f'<div dir="rtl" style="text-align:right">{turn.reply.replace(chr(10), "<br>")}</div>'
        try:
            _send_email(from_email, name, reply_subject, html, turn.reply, internet_msg_id or None)
            print(f"[GMAIL REPLY] to={from_email}")
        except Exception as e:
            print(f"[GMAIL REPLY ERROR] {e}")

        mail.store(num, "+FLAGS", "\\Seen")

        if turn.handoff_to_human:
            updated += "\n[HANDOFF]"
            db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())
            db.mark_reengagement_handoff(f"email:{from_email}")
            _email_sessions.pop(from_email, None)
            print(f"[GMAIL HANDOFF] {from_email}")

    mail.logout()
