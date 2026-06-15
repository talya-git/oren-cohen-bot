"""שכבת API (FastAPI) — לחיבור עתידי לוואטסאפ/אתר.

הרצה:  uvicorn app.main:app --reload
בשלב זה ניהול ה-session הוא בזיכרון (dict). בפרודקשן — Redis/DB.
"""

from pathlib import Path
from uuid import uuid4
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import sehel
from . import ratings
from .engine import Conversation
from .prompts import GREETING
from .leads_api import router as leads_router
from . import database as db

app = FastAPI(title="Oren Cohen Group — Lead Bot")
app.include_router(leads_router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Serve static files (logo, etc.)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def home() -> FileResponse:
    """עמוד הצ'אט בדפדפן."""
    return FileResponse(STATIC_DIR / "index.html")

# session_id -> Conversation  (זמני; להחליף ב-Redis/DB בפרודקשן)
_sessions: dict[str, Conversation] = {}
# מקורות לידים שכבר הוזרקו לשכל (למניעת כפילויות)
_pushed: set[str] = set()


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    media_source: str = "Facebook"  # Facebook / Google / Yad2 / Mislal


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    stage: str
    level: str
    score: float
    handoff_to_human: bool
    sehel_lead_id: str | None = None  # מזהה הליד בשכל (או None אם טרם הוזרק)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Training mode: bot plays as client, user is the agent."""
    if req.session_id and req.session_id in _train_sessions:
        sid = req.session_id
    elif req.session_id and req.session_id not in _train_sessions:
        # session ישן שפג תוקף (restart/sleep)
        return ChatResponse(
            session_id=req.session_id, reply="השיחה הקודמת נסגרה. לחצי 'שיחה חדשה' להתחיל.",
            stage="handoff", level="Low", score=0, handoff_to_human=False,
        )
    else:
        sid = str(uuid4())
        # Create training session - bot as client
        from openai import OpenAI
        import httpx as hx
        client_ai = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=hx.Client(verify=False),
        )
        system = """אתה לקוח שפונה לחברת נדל"ן בירושלים. כתוב קצר וטבעי (משפט-שניים מקסימום).

סוג הלקוח שלך נקבע אקראית בתחילת השיחה:
- 90% מהפעמים: לקוח רגיל שלא אכפת לו למסור פרטים. תקציב/אזור/חדרים - עונה מיד. שם וטלפון - נותן רק כשמבקשים במפורש.
- 5% מהפעמים: לקוח שמהסס קצת. פעם אחת אומר "למה אתה צריך את זה?" או "אני אשמח קודם לשמוע פרטים" אבל אחרי שהסוכן מסביר - נותן.
- 5% מהפעמים: לקוח מאד נוקשה. "אני לא משאיר פרטים לאף אחד" / "זה לא עניינך" / "תפסיק להתקשר" / "הדירות שלכם יקרות". צריך שכנוע מאד רציני.

כללים קריטיים:
- תענה רק למה ששואלים אותך. אל תוסיף מידע שלא ביקשו.
- אם שואלים על הדירה (חדרים/אזור/תקציב) - תענה רק על הדירה. אל תוסיף שם וטלפון אם לא ביקשו.
- שם וטלפון תמסור רק כשהסוכן מבקש במפורש "תשאיר פרטים" או "מה השם שלך?" או "איך אפשר לחזור אליך?".
- תמציא שמות מגוונים, טלפונים מגוונים, תקציבים מגוונים, אזורים מגוונים.
- תרחישים מגוונים: קניה/שכירות/השקעה/מכירה.
- יכול להיות בעברית או באנגלית."""
        _train_sessions[sid] = {
            "messages": [{"role": "system", "content": system}],
            "client": client_ai,
        }
        # Generate first client message
        resp = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=_train_sessions[sid]["messages"] + [{"role": "system", "content": "תבחר תרחיש אקראי ומגוון. תהיה אחד מאלה: משקיע אמריקאי שמחפש וילה, זוג צעיר שמחפש דירה ראשונה, מתווך שמציע נכס למכירה, אישה שמחפשת שכירות לטווח ארוך, אדם שראה מודעה על פרויקט ספציפי, מתווך ששואל על שכירות, אדם שרוצה למכור נכס שלו, מישהו ששואל על מחירים בלי הקדמה, מישהו ששואל על השכרה לסוכות, מישהו ששואל על פרויקט באנגלית, אדם ששולח רק היי בלי הקשר, אדם שכועס על הסוכן. תבחר אחד אקראית ותפתח איתו."}],
            temperature=0.7,
        )
        first_msg = resp.choices[0].message.content.strip()
        _train_sessions[sid]["messages"].append({"role": "assistant", "content": first_msg})
        return ChatResponse(
            session_id=sid, reply=first_msg, stage="greeting",
            level="Medium", score=0.5, handoff_to_human=False,
        )

    # Continue training conversation
    session = _train_sessions.get(sid)
    if not session:
        return ChatResponse(
            session_id=sid, reply="שיחה הסתיימה. לחץ 'שיחה חדשה' להתחיל.",
            stage="handoff", level="Low", score=0, handoff_to_human=True,
        )

    messages = session["messages"]
    client_ai = session["client"]

    # Add agent response
    messages.append({"role": "user", "content": req.message})

    # Generate next client message
    resp = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages + [{"role": "system", "content": "תזכורת: תענה רק למה ששאלו. אם שאלו על הדירה - תענה על הדירה בלבד. אבל אם הסוכן מבקש פרטים ליצירת קשר (כמו 'תשאיר פרטים', 'תשאיר שם וטלפון', 'איך לחזור אליך', 'מה השם שלך', 'נחזור אליך') - תתן מיד שם וטלפון פיקטיביים. אם הסוכן ביקש פרטים ליצירת קשר יותר מפעם אחת - תבין שהוא צריך את זה ותתן שם וטלפון. אם הסוכן אומר שיחזור - תגיד 'בטח, אני דוד 053-7654321'. לא לסיים בלי להשאיר פרטים אם הסוכן ביקש."}],
        temperature=0.5,
    )
    client_msg = resp.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": client_msg})

    # Detect end
    end_phrases = ["יום טוב", "תודה רבה", "להתראות", "ביי", "bye", "thank you", "have a great day", "תודה!"]
    is_done = any(phrase in client_msg.lower() for phrase in end_phrases) and len([m for m in messages if m["role"] == "user"]) >= 3

    if is_done:
        # Save training conversation
        transcript = []
        for m in messages[1:]:
            role = "client" if m["role"] == "assistant" else "agent"
            transcript.append({"role": role, "content": m["content"]})
        ratings.save_feedback(sid, "training", "שיחת אימון", transcript)
        del _train_sessions[sid]
        return ChatResponse(
            session_id=sid, reply=client_msg + "\n\n✅ השיחה נשמרה ללמידה!",
            stage="handoff", level="High", score=1, handoff_to_human=True,
        )

    return ChatResponse(
        session_id=sid, reply=client_msg, stage="engagement",
        level="Medium", score=0.5, handoff_to_human=False,
    )


def _maybe_push_to_sehel(
    sid: str, convo: Conversation, level: str, score: float, media_source: str, handoff: bool
) -> str | None:
    if sid in _pushed:
        return None
    if not (handoff or level == "High"):
        return None
    if not convo.profile.phone:
        return None  # שכל דורש טלפון

    # אם אין project_id ואין webhook — dry-run (לא שולח בפועל)
    dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
    try:
        payload = sehel.build_payload(convo.profile, level, score, media_source=media_source)
        result = sehel.push_lead(payload, dry_run=dry)
    except Exception:
        return None  # כשל בשכל לא ישבור את השיחה

    _pushed.add(sid)
    return result.get("leadId") if not dry else "DRY_RUN"


@app.get("/greeting")
def greeting() -> dict:
    return {"reply": GREETING}


@app.get("/session/{session_id}/profile")
def get_profile(session_id: str) -> dict:
    """הפרופיל המצטבר — מה שיוזרק ל'שכל'."""
    convo = _sessions.get(session_id)
    if not convo:
        raise HTTPException(404, "session not found")
    return convo.profile.model_dump()


class RatingRequest(BaseModel):
    session_id: str
    color: str  # red / orange / green


@app.post("/rate")
def rate_lead(req: RatingRequest) -> dict:
    """שמירת דירוג ליד."""
    convo = _sessions.get(req.session_id)
    profile = convo.profile.model_dump() if convo else {}
    transcript = convo.messages if convo else []
    ratings.save_rating(req.session_id, req.color, profile, transcript)
    return {"status": "saved"}


class FeedbackRequest(BaseModel):
    session_id: str
    rating: str  # good / bad
    notes: str = ""


@app.post("/feedback")
def save_feedback(req: FeedbackRequest) -> dict:
    """שמירת פידבק על איכות השיחה."""
    convo = _sessions.get(req.session_id)
    transcript = convo.messages if convo else []
    ratings.save_feedback(req.session_id, req.rating, req.notes, transcript)
    return {"status": "saved"}


@app.get("/leads")
def leads_page() -> FileResponse:
    """מערכת לידים."""
    return FileResponse(STATIC_DIR / "leads.html")


class CreateLeadRequest(BaseModel):
    session_id: str
    rating: str = "none"


def _extract_profile_from_transcript(messages: list) -> dict:
    """מחלץ שם, טלפון, תקציב, אזור, חדרים מהודעות הלקוח (רול assistant)."""
    import re
    profile = {}
    client_msgs = " ".join([m["content"] for m in messages if m.get("role") == "assistant"])

    # טלפון
    phone_match = re.search(r'0[5-9]\d[- ]?\d{3}[- ]?\d{4}', client_msgs)
    if phone_match:
        profile["phone"] = phone_match.group()

    # שם - מחפש אחרי "אני" או "שמי"
    name_patterns = [
        r'אני ([\u05d0-\u05ea]+ [\u05d0-\u05ea]+)',
        r'שמי ([\u05d0-\u05ea]+ [\u05d0-\u05ea]+)',
        r'שמי ([\u05d0-\u05ea]+)',
        r'אני ([\u05d0-\u05ea]+)',
        r'([A-Z][a-z]+ [A-Z][a-z]+)',
    ]
    for pat in name_patterns:
        name_match = re.search(pat, client_msgs)
        if name_match:
            profile["contact_name"] = name_match.group(1)
            break

    # תקציב
    budget_match = re.search(r'(\d[\d,.]+)\s*(מיליון|million|M)', client_msgs)
    if budget_match:
        profile["budget_ils"] = budget_match.group(0)
    budget_match2 = re.search(r'עד\s*(\d[\d,.]+)', client_msgs)
    if not profile.get("budget_ils") and budget_match2:
        profile["budget_ils"] = budget_match2.group(0)

    # חדרים
    rooms_match = re.search(r'(\d)\s*חדרים', client_msgs)
    if rooms_match:
        profile["rooms"] = rooms_match.group(1)
    rooms_match2 = re.search(r'(\d)\s*rooms|bedroom', client_msgs, re.IGNORECASE)
    if not profile.get("rooms") and rooms_match2:
        profile["rooms"] = rooms_match2.group(1)

    # אזור
    areas = ['רחביה', 'ארנונה', 'בקעה', 'טלביה', 'מושבה גרמנית', 'מרכז העיר',
            'German Colony', 'Rehavia', 'Talbiya', 'Arnona', 'Baka',
            'קטמון', 'נחלאות', 'גילו', 'עיר גנים', 'פסגת זאב']
    for area in areas:
        if area.lower() in client_msgs.lower():
            profile["area"] = area
            break

    # כוונה
    if any(kw in client_msgs for kw in ['שכירות', 'להשכרה', 'להשכיר', 'לשכור']):
        profile["intent"] = 'שכירות'
    elif any(kw in client_msgs for kw in ['קניה', 'לקנות', 'לקנייה', 'לרכוש']):
        profile["intent"] = 'קניה'
    elif any(kw in client_msgs for kw in ['השקעה', 'להשקיע', 'השקעה']):
        profile["intent"] = 'השקעה'
    elif 'rent' in client_msgs.lower():
        profile["intent"] = 'שכירות'
    elif 'buy' in client_msgs.lower():
        profile["intent"] = 'קניה'
    elif 'invest' in client_msgs.lower():
        profile["intent"] = 'השקעה'

    # תוספות (amenities) - רק אם הלקוח ביקש במפורש
    amenities = []
    amenity_keywords = {
        'מרפסת': ['רוצה מרפסת', 'חשוב לי מרפסת', 'מרפסת זה חשוב', 'מרפסת חובה', 'צריך מרפסת', 'עם מרפסת'],
        'מחסן': ['רוצה מחסן', 'חשוב לי מחסן', 'מחסן חשוב', 'צריך מחסן'],
        'חניה': ['רוצה חניה', 'חשוב לי חניה', 'חניה חשוב', 'צריך חניה', 'עם חניה'],
        'ממד': ['רוצה ממד', 'חשוב לי ממד', 'ממד חשוב', 'צריך ממד'],
        'מעלית': ['רוצה מעלית', 'חשוב לי מעלית', 'צריך מעלית'],
        'גישה לנכים': ['רוצה גישה לנכים', 'נגישות'],
        'נוף': ['רוצה נוף', 'חשוב לי נוף', 'נוף חשוב', 'צריך נוף', 'עם נוף'],
    }
    for amenity, keywords in amenity_keywords.items():
        if any(kw in client_msgs for kw in keywords):
            amenities.append(amenity)
    if amenities:
        import json as json_mod
        profile["amenities"] = json_mod.dumps(amenities, ensure_ascii=False)

    # קרבה ל (nearBy) - רק אם הלקוח ביקש במפורש
    nearby = []
    nearby_keywords = {
        'בית כנסת': ['רוצה קרוב לבית כנסת', 'חשוב לי בית כנסת', 'קרוב לבתי כנסיות', 'ליד בית כנסת'],
        'סופרים': ['רוצה קרוב לסופר', 'חשוב לי סופר', 'קרוב לסופרים', 'ליד סופר', 'קרבה לסופרים'],
    }
    for place, keywords in nearby_keywords.items():
        if any(kw in client_msgs for kw in keywords):
            nearby.append(place)
    if nearby:
        import json as json_mod
        profile["nearBy"] = json_mod.dumps(nearby, ensure_ascii=False)

    return profile


@app.post("/create-lead")
def create_lead_from_chat(req: CreateLeadRequest) -> dict:
    """שולח ליד למערכת הלידים עם הנתונים מהשיחה."""
    import httpx
    import json as json_lib

    # משיג את התמליל מה-train session
    session = _train_sessions.get(req.session_id)
    if not session:
        # גם מ-_sessions (שיחה אמיתית)
        convo = _sessions.get(req.session_id)
        if convo:
            profile = convo.profile.model_dump()
            transcript = convo.messages
        else:
            return {"status": "error", "detail": "session not found"}
    else:
        # train session - חילוץ תמליל
        if isinstance(session, dict):
            messages = session.get("messages", [])
        else:
            messages = session
        transcript = []
        for m in messages[1:]:
            role = "client" if m["role"] == "assistant" else "agent"
            transcript.append({"role": role, "content": m["content"]})
        # חילוץ פרטים מהתמליל (הלקוח = assistant = client)
        profile = _extract_profile_from_transcript(messages)

    # ממפה rating color לפורמט של ה-API
    rating_map = {"red": "hot", "orange": "warm", "green": "cold"}
    rating = rating_map.get(req.rating, "none")

    # בונה את ה-payload
    lead_data = {
        "contactName": profile.get("contact_name"),
        "phone": profile.get("phone"),
        "budget": str(profile.get("budget_ils", "")) if profile.get("budget_ils") else None,
        "area": profile.get("area"),
        "rooms": str(profile.get("rooms", "")) if profile.get("rooms") else None,
        "propertyType": None,
        "floor": None,
        "financing": profile.get("financing"),
        "timeline": profile.get("timeline"),
        "intent": profile.get("intent"),
        "amenities": profile.get("amenities"),
        "airDirections": profile.get("airDirections"),
        "nearBy": profile.get("nearBy"),
        "transcript": json_lib.dumps(transcript, ensure_ascii=False) if transcript else None,
    }

    # שולח ל-API של הלידים
    leads_api_url = os.getenv("LEADS_API_URL", "https://localhost:7177")
    try:
        # קודם מתחבר כמנהל כדי לקבל token
        login_res = httpx.post(
            f"{leads_api_url}/api/auth/login",
            json={"name": "מנהל", "password": "1234"},
            verify=False, timeout=10
        )
        if login_res.status_code != 200:
            return {"status": "error", "detail": "login failed"}
        token = login_res.json()["token"]

        # יוצר ליד
        create_res = httpx.post(
            f"{leads_api_url}/api/leads",
            json=lead_data,
            headers={"Authorization": f"Bearer {token}"},
            verify=False, timeout=10
        )

        if create_res.status_code in (200, 201):
            lead_id = create_res.json().get("id")
            # מעדכן דירוג
            if rating != "none" and lead_id:
                httpx.put(
                    f"{leads_api_url}/api/leads/{lead_id}",
                    json={"rating": rating},
                    headers={"Authorization": f"Bearer {token}"},
                    verify=False, timeout=10
                )
            return {"status": "ok", "lead_id": lead_id}
        else:
            return {"status": "error", "detail": create_res.text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/dashboard")
def dashboard() -> FileResponse:
    """דף דשבורד לצפייה בדירוגים ופידבק."""
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/ratings")
def api_ratings() -> list:
    return ratings.get_all_ratings()


# === Training Mode ===
_train_sessions: dict[str, list] = {}


@app.get("/train")
def train_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "train.html")


@app.post("/train/end")
def train_end(req: dict) -> dict:
    """סיום ושמירת שיחת אימון ידנית (כפתור שיחה חדשה)."""
    sid = req.get("session_id", "")
    messages = _train_sessions.get(sid, [])
    if not messages:
        return {"status": "no_session"}
    transcript = []
    for m in messages[1:]:
        role = "client" if m["role"] == "assistant" else "agent"
        transcript.append({"role": role, "content": m["content"]})
    ratings.save_feedback(sid, "training", "שיחת אימון (סיום ידני)", transcript)
    del _train_sessions[sid]
    return {"status": "saved"}


@app.post("/train/start")
def train_start() -> dict:
    """מתחיל שיחת אימון — הבוט משחק לקוח."""
    from openai import OpenAI
    import httpx
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=httpx.Client(verify=False),
    )
    sid = str(uuid4())
    system = """אתה לקוח שפונה לחברת נדל"ן בירושלים. כתוב קצר וטבעי (משפט-שניים מקסימום).

סוג הלקוח שלך נקבע אקראית בתחילת השיחה:
- 90% מהפעמים: לקוח רגיל שלא אכפת לו למסור פרטים. תקציב/אזור/חדרים - עונה מיד. שם וטלפון - נותן רק כשמבקשים במפורש.
- 5% מהפעמים: לקוח שמהסס קצת. פעם אחת אומר "למה אתה צריך את זה?" או "אני אשמח קודם לשמוע פרטים" אבל אחרי שהסוכן מסביר - נותן.
- 5% מהפעמים: לקוח מאד נוקשה. "אני לא משאיר פרטים לאף אחד" / "זה לא עניינך" / "תפסיק להתקשר" / "הדירות שלכם יקרות". צריך שכנוע מאד רציני.

כללים קריטיים:
- תענה רק למה ששואלים אותך. אל תוסיף מידע שלא ביקשו.
- אם שואלים על הדירה (חדרים/אזור/תקציב) - תענה רק על הדירה. אל תוסיף שם וטלפון אם לא ביקשו.
- שם וטלפון תמסור רק כשהסוכן מבקש במפורש "תשאיר פרטים" או "מה השם שלך?" או "איך אפשר לחזור אליך?".
- תמציא שמות מגוונים, טלפונים מגוונים, תקציבים מגוונים, אזורים מגוונים.
- תרחישים מגוונים: קניה/שכירות/השקעה/מכירה.
- יכול להיות בעברית או באנגלית."""

    messages = [{"role": "system", "content": system}]
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.7
    )
    client_msg = resp.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": client_msg})
    _train_sessions[sid] = messages
    return {"session_id": sid, "client_message": client_msg}


@app.post("/train/respond")
def train_respond(req: dict) -> dict:
    """הסוכן עונה, הבוט ממשיך כלקוח."""
    from openai import OpenAI
    import httpx
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        http_client=httpx.Client(verify=False),
    )
    sid = req.get("session_id", "")
    agent_response = req.get("agent_response", "")
    messages = _train_sessions.get(sid, [])

    if not messages:
        return {"done": True}

    messages.append({"role": "user", "content": agent_response})

    # Check if conversation should end naturally
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages + [{"role": "system", "content": "תזכורת: אתה לקוח שלא אכפת לו למסור פרטים. אם הסוכן אומר 'תשאיר פרטים' - תגיד מיד 'בטח, אני יוסי, 052-3456789'. אם הסוכן אומר שיחזור אליך - תגיד 'תודה, יום טוב'. לעולם אל תגיד 'למה?' או 'אני רק רוצה לשמוע' או 'אני אחשוב'."}],
        temperature=0.5
    )
    client_msg = resp.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": client_msg})
    _train_sessions[sid] = messages

    # Detect end of conversation
    end_phrases = ["יום טוב", "תודה רבה", "להתראות", "ביי", "bye", "thank you", "have a great day"]
    is_done = any(phrase in client_msg.lower() for phrase in end_phrases) and len([m for m in messages if m["role"] == "user"]) >= 3

    if is_done:
        # Save the training conversation
        transcript = []
        for m in messages[1:]:
            role = "client" if m["role"] == "assistant" else "agent"
            transcript.append({"role": role, "content": m["content"]})
        ratings.save_feedback(sid, "training", "שיחת אימון", transcript)
        del _train_sessions[sid]
        return {"done": True, "client_message": client_msg}

    return {"done": False, "client_message": client_msg}


@app.delete("/api/ratings/{index}")
def delete_rating(index: int) -> dict:
    all_ratings = ratings.get_all_ratings()
    if 0 <= index < len(all_ratings):
        all_ratings.pop(index)
        ratings._save(ratings.RATINGS_BIN, all_ratings)
    return {"status": "deleted"}


@app.get("/api/feedback")
def api_feedback() -> list:
    return ratings.get_all_feedback()


@app.delete("/api/feedback/{index}")
def delete_feedback(index: int) -> dict:
    all_feedback = ratings.get_all_feedback()
    if 0 <= index < len(all_feedback):
        all_feedback.pop(index)
        ratings._save(ratings.FEEDBACK_BIN, all_feedback)
    return {"status": "deleted"}
