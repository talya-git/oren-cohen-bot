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

        # חיתוך quote - קודם כל דבר אחר
        cut_markers = ["מאת:", "From:", "-----Original", "________________________________",
                       "wrote:", "כתב:", "נשלח:", "Sent:",
                       "daniel@orencohengroup.com",
                       "ocgdaniel@gmail.com", "Daniel | Oren Cohen Group",
                       "On ", "> "]
        earliest = len(text)
        for marker in cut_markers:
            idx = text.find(marker)
            if 0 < idx < earliest:
                earliest = idx
        if earliest > 2:
            text = text[:earliest].strip()
        # נקה קווים תחתונים ותווים עודפים
        text = re.sub(r'[_\-]{4,}', '', text)
        text = re.sub(r"\s+", " ", text).strip()
        # אם הטקסט ריק לגמרי אחרי הניקוי - התשובה היית בתוך ה-quote
        if not text:
            mail.store(num, "+FLAGS", "\\Seen")
            print(f"[GMAIL SKIP] empty text after cut")
            continue

        if not text:
            mail.store(num, "+FLAGS", "\\Seen")
            continue

        print(f"[GMAIL INBOUND] from={from_email} subject={subject}")

        name = record.get("client_name") or ""
        # שפת פתיחה לפי שם, בהמשך לפי הטקסט שלקוח
        name_is_hebrew = name and any('\u05d0' <= c <= '\u05ea' for c in name)
        he_chars = sum(1 for c in text if '\u05d0' <= c <= '\u05ea')
        en_chars = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        if he_chars > 0 or en_chars > 0:
            # יש טקסט בריר — זיהוי לפי התשובה
            lang = "he" if he_chars >= en_chars else "en"
        else:
            # אין תווים ברורים — זיהוי לפי שם
            lang = "he" if (not name or name_is_hebrew) else "en"

        # בנה session חדש מהטרנסקריפט הנוכחי ב-DB (כולל כל ההיסטוריה)
        transcript = record.get("transcript") or ""

        # אם כבר היה handoff — לא לענות
        if record.get("handoff") or "[HANDOFF]" in transcript:
            mail.store(num, "+FLAGS", "\\Seen")
            print(f"[GMAIL SKIP] handoff already done for {from_email}")
            continue

        convo = _build_convo_from_transcript(transcript, lang)
        convo._language = lang
        # בנה system prompt בשפה הנכונה לפני send()
        if not convo._system_built:
            from .engine import Conversation as _Conv
            system = _Conv._build_system(convo, lang)
            convo.messages.insert(0, {"role": "system", "content": system})
            convo._system_built = True

        # אם אין היסטוריה — הלקוח עונה לראשונה
        if not convo.messages:
            convo.messages.append({"role": "assistant", "content": "האם הנושא עדיין רלוונטי עבורך?"})

        # שמור ב-sessions
        _email_sessions[from_email] = convo

        # זיהוי תשובה שלילית לפני חיובית
        negative_words = ["לא רלוונטי", "לא מעוניין", "לא כרגע", "לא עכשיו", "לא צריך",
                          "לא רלוונטי בשבילי", "לא רלוונטי עבורי", "לא רלוונטי לי","לא"
                          "not relevant", "not interested", "no thanks", "not now"]
        is_negative = any(w in text.lower() for w in negative_words)

        # זיהוי תשובה חיובית לשאלת הפתיחה
        positive_words = ["כן", "מעוניין", "מעוניינת", "אשמח", "בטח", "כמובן", "yes", "interested", "sure", "absolutely"]
        is_first_reply = len([m for m in convo.messages if m["role"] == "user"]) == 0
        is_positive = not is_negative and any(w in text.lower() for w in positive_words)

        if is_first_reply and is_positive:
            actual_text = f"[הלקוח ענה חיובית: '{text}'. ענה מיד בהודעת ההעברה לסוכן והלינק לאתר. אל תשאל שאלות נוספות.]"
        else:
            actual_text = text

        # שלח את ההודעה לבוט
        turn, score = convo.send(actual_text)

        # עדכון תמליל ב-DB — שמור רק את התשובה הנקייה
        clean_text = text[:200]  # מקסימום 200 תווים מהתשובה
        updated = transcript + f"\nClient: {clean_text}\nDaniel: {turn.reply}"
        db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())

        # נקה מקפים מהתשובה
        reply_text = turn.reply.replace('\u2014', ',').replace('\u2013', ',')

        # שליחת תשובה
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
        html_dir = "ltr" if lang == "en" else "rtl"
        html_align = "left" if lang == "en" else "right"
        html = f'<div dir="{html_dir}" style="text-align:{html_align}">{reply_text.replace(chr(10), "<br>")}</div>'
        try:
            _send_email(from_email, name, reply_subject, html, reply_text, internet_msg_id or None)
            print(f"[GMAIL REPLY] to={from_email}")
        except Exception as e:
            print(f"[GMAIL REPLY ERROR] {e}")

        mail.store(num, "+FLAGS", "\\Seen")

        if turn.handoff_to_human:
            is_relevant = not ("נשמח שתשמור" in turn.reply or "we'd love to stay" in turn.reply.lower())
            updated += "\n[HANDOFF]"
            db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())
            if is_relevant:
                db.mark_reengagement_handoff(f"email:{from_email}")
            _email_sessions.pop(from_email, None)
            print(f"[GMAIL HANDOFF] {from_email} relevant={is_relevant}")
            from . import sehel as _sehel
            dry = not (_sehel.PROJECT_ID or _sehel.WEBHOOK_URL)
            agent_email = record.get("agent_email") or ""
            _sehel.update_lead_after_conversation(
                from_email,
                updated,
                is_relevant=is_relevant,
                agent_email=agent_email,
                client_name=name,
                channel="Email",
                dry_run=dry,
            )

    mail.logout()
