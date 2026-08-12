"""Microsoft Graph API — סריקת תיבת דואר נכנס ותגובה אוטומטית."""

import os
import json
import urllib.request
import urllib.parse
import urllib.error

TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
BOT_EMAIL = os.getenv("BOT_EMAIL", "daniel@orencohengroup.com")

_access_token: str | None = None
_processed_ids: set = set()  # message IDs שכבר טופלו


def _get_token() -> str:
    global _access_token
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        _access_token = json.loads(resp.read().decode())["access_token"]
    return _access_token


def _graph(path: str, method: str = "GET", body: dict | None = None) -> dict:
    token = _get_token()
    url = f"https://graph.microsoft.com/v1.0{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _mark_read(msg_id: str):
    _graph(f"/users/{BOT_EMAIL}/messages/{msg_id}", method="PATCH", body={"isRead": True})


def _reply_email(to_email: str, to_name: str, subject: str, reply_text: str):
    from .email_api import _send_email
    html = reply_text.replace("\n", "<br>")
    _send_email(to_email, to_name, subject, f"<p>{html}</p>", reply_text)


def poll_inbox():
    """סורק מיילים חדשים שלא נקראו ועונה עליהם."""
    from .engine import Conversation
    from . import database as db
    from .email_api import _email_sessions

    try:
        params = urllib.parse.urlencode({
            "$filter": "isRead eq false",
            "$select": "id,from,subject,body",
            "$top": "10",
        })
        result = _graph(f"/users/{BOT_EMAIL}/mailFolders/inbox/messages?{params}")
    except Exception as e:
        print(f"[EMAIL POLL ERROR] {e}")
        return

    for msg in result.get("value", []):
        msg_id = msg["id"]

        if msg_id in _processed_ids:
            continue
        _processed_ids.add(msg_id)
        sender = msg.get("from", {}).get("emailAddress", {})
        from_email = sender.get("address", "").lower()
        from_name = sender.get("name", "")
        subject = msg.get("subject", "Re: Jerusalem Real Estate")
        body_content = msg.get("body", {}).get("content", "")

        # הסרת HTML tags
        import re
        text = re.sub(r"<[^>]+>", " ", body_content).strip()
        text = re.sub(r"\s+", " ", text).strip()

        if not from_email or from_email == BOT_EMAIL.lower() or "mailjet.com" in from_email or "noreply" in from_email:
            _mark_read(msg_id)
            continue

        print(f"[EMAIL INBOUND] from={from_email} subject={subject}")

        # שחזור session
        if from_email not in _email_sessions:
            record = db.get_reengagement_record(f"email:{from_email}")
            convo = Conversation(language="en")
            if record and record.get("transcript"):
                for line in record["transcript"].split("\n"):
                    line = line.strip()
                    if line.startswith("Daniel:"):
                        convo.messages.append({"role": "assistant", "content": line[7:].strip()})
                    elif line.startswith("Client:"):
                        convo.messages.append({"role": "user", "content": line[7:].strip()})
            _email_sessions[from_email] = convo

        convo = _email_sessions[from_email]
        turn, score = convo.send(text)

        # עדכון תמליל
        record = db.get_reengagement_record(f"email:{from_email}")
        existing = (record.get("transcript") or "") if record else ""
        updated = existing + f"\nClient: {text}\nDaniel: {turn.reply}"
        db.update_reengagement_replied(f"email:{from_email}", True, updated.strip())

        # שליחת תשובה
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
        try:
            _reply_email(from_email, from_name, reply_subject, turn.reply)
            print(f"[EMAIL REPLY] to={from_email}")
        except Exception as e:
            print(f"[EMAIL REPLY ERROR] {e}")

        _mark_read(msg_id)

        if turn.handoff_to_human:
            _email_sessions.pop(from_email, None)
            print(f"[EMAIL HANDOFF] {from_email}")
