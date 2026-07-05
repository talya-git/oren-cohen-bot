"""שליחת הודעות WhatsApp דרך UltraMsg."""

import time
import requests

INSTANCE_ID = "instance183747"
TOKEN = "3mfx8x4sw1bv4496"
BASE_URL = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"

MESSAGE_HE = """שלום,

אני פונה אליך בעקבות עניינך בפרויקט השלושה רזידנס, פיתוח בוטיק יוקרתי הממוקם בלב ירושלים.

נכון להיום, נותרו למכירה בפרויקט שלושה דירות בלבד. אם הפרויקט מעניין אותך, נשמח אם תפנה אלינו בהקדם האפשרי, כדי שנוכל לסייע לך ברכישת דירה באחד הפיתוחים היוקרתיים והייחודיים ביותר בירושלים.

אם בסופו של דבר תחליט שהשלושה רזידנס אינו עונה בדיוק על צרכיך, אנו משווקים גם מספר פרויקטים בלעדיים נוספים ונשמח להציג בפניך חלופות שעשויות להתאים לך יותר.

אל תהסס לפנות אלינו בכל עת. נשמח לסייע לך במציאת הנכס המתאים ביותר עבורך.

בברכה,
דב רבינוביץ
אורן כהן גרופ – נדל"ן ירושלים
052-6239608
https://www.orencohengroup.com/development/jerusalem-german-colony-new-project/"""

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
    })
    return resp.json()


def send_test():
    for phone in TEST_PHONES:
        result = send_message(phone, MESSAGE_HE)
        print(f"{phone} → {result}")
        time.sleep(2)  # המתנה בין הודעות


# === FastAPI endpoint להפעלה מרחוק ===
from fastapi import APIRouter
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

@router.post("/test")
def test_send():
    results = []
    for phone in TEST_PHONES:
        result = send_message(phone, MESSAGE_HE)
        results.append({"phone": phone, "result": result})
        time.sleep(2)
    return results


if __name__ == "__main__":
    send_test()
