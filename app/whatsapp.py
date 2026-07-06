"""שליחת הודעות WhatsApp דרך UltraMsg."""

import time
import requests

INSTANCE_ID = "instance183747"
TOKEN = "3mfx8x4sw1bv4496"
BASE_URL = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"

MESSAGE_HE = "היי, אני דניאל ממשרד אורן כהן גרופ 😊 ראיתי שבעבר פנית אלינו בנושא קניית דירה בירושלים — האם זה עדיין רלוונטי עבורך?"

TEST_PHONES = [
    "+972526239608",
    "+13055863760",
    "+972504183337",
]


def send_message(phone: str, message: str) -> dict:
    resp = requests.post(BASE_URL, data={
        "token": TOKEN,
        "to": phone,
        "body": message,
        "priority": 10,
    }, verify=False)
    return resp.json()


def send_reengagement(phone: str) -> dict:
    return send_message(phone, MESSAGE_HE)


def send_test():
    for phone in TEST_PHONES:
        result = send_message(phone, MESSAGE_HE)
        print(f"{phone} → {result}")
        time.sleep(2)


# === FastAPI endpoint להפעלה מרחוק ===
from fastapi import APIRouter, Request
from pydantic import BaseModel
from uuid import uuid4

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# session_id לפי מספר טלפון
_wa_sessions: dict = {}


@router.post("/test")
def test_send():
    results = []
    for phone in TEST_PHONES:
        result = send_message(phone, MESSAGE_HE)
        results.append({"phone": phone, "result": result})
        time.sleep(2)
    return results


class SendRequest(BaseModel):
    phone: str


@router.post("/send-reengagement")
def send_reengagement_endpoint(req: SendRequest):
    """שולח הודעת re-engagement ופותח session שיחה."""
    from .engine import Conversation
    _wa_sessions[req.phone] = Conversation()
    result = send_reengagement(req.phone)
    return {"status": "sent", "result": result}


# ביטויים לזיהוי כוונה
_NOT_RELEVANT = ["לא רלוונטי", "לא מעוניין", "לא רלוונט", "לא מתעניין", "לא צריך", "לא רוצה", "not relevant", "not interested"]
_SNOOZE_WEEK = ["עסוק", "אחר כך", "אחרי", "יחשוב", "אחשוב", "לא עכשיו", "busy", "later", "will think", "not now"]


def _classify_response(msg: str) -> str:
    """מחזיר: 'not_relevant' / 'snooze_week' / 'continue'"""
    lower = msg.lower()
    if any(p in lower for p in _NOT_RELEVANT):
        return "not_relevant"
    if any(p in lower for p in _SNOOZE_WEEK):
        return "snooze_week"
    return "continue"


def _save_followup(phone: str, weeks: int, reason: str) -> None:
    """שומר ליד לטיפול עתידי ב-data/followups.json"""
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
    data = await request.json()
    print(f"[WEBHOOK] {data}")
    # UltraMsg עוטף את הנתונים בתוך data["data"]
    msg = data.get("data") or data
    phone = msg.get("from", "").replace("@c.us", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    user_msg = msg.get("body", "").strip()

    if not user_msg or msg.get("fromMe") or msg.get("type", "chat") != "chat":
        return {"status": "ignored"}

    # אם אין session פעיל — זו תשובה להודעת ה-re-engagement
    if phone not in _wa_sessions:
        intent = _classify_response(user_msg)
        if intent == "not_relevant":
            _save_followup(phone, weeks=26, reason="not_relevant")
            send_message(phone, "מובן, תודה על התשובה! אם בעתיד תתעניין — אנחנו כאן 😊")
            return {"status": "snoozed_26w"}
        if intent == "snooze_week":
            _save_followup(phone, weeks=1, reason="snooze")
            send_message(phone, "בטח, אחזור אליך בשבוע הבא! 😊")
            return {"status": "snoozed_1w"}
        # רלוונטי — פתח שיחה עם context של re-engagement
        from .engine import Conversation
        conv = Conversation()
        # הזרק הודעת פתיחה שמסבירה שהלקוח כבר אמר שהוא מעוניין
        conv.messages.append({
            "role": "user",
            "content": f"[הקשר: הלקוח קיבל הודעת re-engagement ועונה שהוא מעוניין. תגובתו: '{user_msg}'. אל תברך שוב בשלום וברכה — המשך ישירות לשאלת הצרכים: אזור, גודל, סוג דירה, דרישות, ורק בסוף תקציב.]"
        })
        conv.messages.append({
            "role": "assistant",
            "content": '{"reply": "", "stage": "intent", "extracted": {}, "handoff_to_human": false, "notes": "re-engagement context injected"}'
        })
        _wa_sessions[phone] = conv

    turn, score = _wa_sessions[phone].send(user_msg)
    time.sleep(7)
    send_message(phone, turn.reply)

    if turn.handoff_to_human:
        del _wa_sessions[phone]

    return {"status": "ok"}


if __name__ == "__main__":
    send_test()
