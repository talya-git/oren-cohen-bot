"""שכבת API (FastAPI) — לחיבור עתידי לוואטסאפ/אתר.

הרצה:  uvicorn app.main:app --reload
בשלב זה ניהול ה-session הוא בזיכרון (dict). בפרודקשן — Redis/DB.
"""

from pathlib import Path
from uuid import uuid4
import os

import json as _json
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import sehel
from . import ratings
from .engine import Conversation
from .prompts import GREETING
from .leads_api import router as leads_router
from .whatsapp import router as whatsapp_router
from .email_api import router as email_router
from . import database as db

class _UTF8JSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return _json.dumps(content, ensure_ascii=False).encode("utf-8")


app = FastAPI(title="Oren Cohen Group — Lead Bot", default_response_class=_UTF8JSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://crm.sehel.co.il"],
    allow_methods=["POST", "GET", "OPTIONS", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(leads_router)
app.include_router(whatsapp_router)
app.include_router(email_router)


@app.on_event("startup")
async def start_morning_reminders():
    import asyncio
    from datetime import datetime, timezone, timedelta

    async def _reminder_loop():
        while True:
            now = datetime.now(timezone.utc).astimezone()
            # חכה עד 9:00 בבוקר
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            try:
                await send_morning_reminders()
            except Exception as e:
                print(f"[REMINDER ERROR] {e}")

    asyncio.create_task(_reminder_loop())


async def send_morning_reminders():
    from datetime import date
    import requests as _req
    from .whatsapp import _token, META_PHONE_NUMBER_ID, META_API_VERSION

    today = date.today()
    day_names = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']
    date_str = f"יום {day_names[today.weekday()]} {today.strftime('%d/%m')}"

    def _send_wa_template(phone: str, template: str, params: list):
        normalized = phone.lstrip("+").replace("-", "").replace(" ", "")
        resp = _req.post(
            f"https://graph.facebook.com/{META_API_VERSION}/{META_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": normalized,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": "he"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
                }
            },
            timeout=15
        )
        return resp.status_code

    AGENTS = [
        {"שם": "בועז",   "phone": "+972545596052"},
        {"שם": "יהודית", "phone": "+972584770646"},
        {"שם": "מוישי",  "phone": "+972523873383"},
        {"שם": "רבקה",   "phone": "+972586455059"},
        {"שם": "מיכאל",  "phone": "+972584114686"},
        {"שם": "מירי",    "phone": "+972543402018"},
        {"שם": "אהרון",  "phone": "+972549183150"},
        {"שם": "אריה",    "phone": "+972552704922"},
        {"שם": "דב",     "phone": "+972526239608"},
        {"שם": "ליסה",    "phone": "+13055863760"},
        {"שם": "נעמי",    "phone": "+972515528956"},
    ]

    for agent in AGENTS:
        try:
            status = _send_wa_template(agent["phone"], "agent_morning_reminder", [agent["שם"]])
            print(f"[REMINDER WA] {agent['שם']} -> {status}")
        except Exception as e:
            print(f"[REMINDER WA ERROR] {agent['שם']}: {e}")

    # רוני — template נפרד עם תאריך
    try:
        status = _send_wa_template("+972528962040", "manager_morning_reminder", [date_str])
        print(f"[REMINDER WA] Roni -> {status}")
    except Exception as e:
        print(f"[REMINDER WA ERROR] Roni: {e}")


@app.on_event("startup")
async def start_report_scheduler():
    import asyncio
    async def _scheduler():
        while True:
            await asyncio.sleep(86400)  # 24 שעות
            try:
                from . import database as _db
                from .mailer import send_report
                for batch in _db.get_pending_batches():
                    leads = _db.get_batch_leads(batch["id"])
                    send_report(
                        to_email=batch["agent_email"],
                        agent_label=batch["agent_label"] or batch["agent_email"],
                        leads=[{
                            "name": l.get("client_name"),
                            "phone": l.get("phone"),
                            "sent": True,
                            "replied": bool(l.get("replied")),
                            "transcript": l.get("transcript") or "",
                            "sent_at": l.get("sent_at"),
                        } for l in leads]
                    )
                    _db.mark_batch_report_sent(batch["id"])
                    print(f"[REPORT] sent to {batch['agent_email']} batch={batch['id']}")
            except Exception as e:
                print(f"[REPORT ERROR] {e}")
    asyncio.create_task(_scheduler())


@app.on_event("startup")
async def start_stalled_scheduler():
    import asyncio
    async def _stalled_scheduler():
        while True:
            await asyncio.sleep(15 * 60)  # 15 דקות
            try:
                from . import database as _db
                from . import sehel as _sehel
                from .schemas import ExtractedParams
                stalled = _db.get_stalled_conversations(hours=2)
                for row in stalled:
                    phone = row.get("phone", "")
                    try:
                        profile = ExtractedParams(
                            phone=phone,
                            contact_name=row.get("client_name") or None,
                        )
                        payload = _sehel.build_payload(
                            profile, "Medium", 0.5,
                            media_source="WhatsApp",
                            no_response=False,
                            transcript=None,
                        )
                        payload["tags[]"] = payload.get("tags[]", []) + ["לא השלים שיחה", "ליד בינוני", "בוט"]
                        # הוסף תמליל מה-DB
                        if row.get("transcript"):
                            payload["lead_comment"] = row["transcript"]
                        dry = not (_sehel.PROJECT_ID or _sehel.WEBHOOK_URL)
                        _sehel.push_lead(payload, dry_run=dry)
                        _db.mark_stalled_pushed(phone)
                        print(f"[STALLED->SEHEL] {phone} | {row.get('client_name')}")
                    except Exception as e:
                        print(f"[STALLED ERROR] {phone}: {e}")
            except Exception as e:
                print(f"[STALLED SCHEDULER ERROR] {e}")
    asyncio.create_task(_stalled_scheduler())


@app.on_event("startup")
async def start_email_poller():
    import asyncio
    async def _email_poll_loop():
        await asyncio.sleep(10)
        while True:
            try:
                from .gmail_poller import poll_inbox
                poll_inbox()
            except Exception as e:
                print(f"[EMAIL POLLER ERROR] {e}")
            await asyncio.sleep(30)
    asyncio.create_task(_email_poll_loop())


@app.on_event("startup")
async def start_no_response_scheduler():
    import asyncio
    async def _no_response_scheduler():
        while True:
            await asyncio.sleep(24 * 60 * 60)  # 24 שעות
            try:
                from . import database as _db
                from . import sehel as _sehel
                rows = _db.get_no_response_conversations(hours=24)
                for row in rows:
                    phone = row.get("phone", "")
                    name = row.get("client_name") or ""
                    try:
                        _sehel.log_call_summary(
                            phone,
                            f"בוט וואטסאפ — נשלחה הודעה ל{name} ולא היה מענה בתוך 24 שעות.",
                            dry_run=not (_sehel.PROJECT_ID or _sehel.WEBHOOK_URL)
                        )
                        _db.mark_stalled_pushed(phone)
                        print(f"[NO-RESPONSE->SEHEL] {phone} | {name}")
                    except Exception as e:
                        print(f"[NO-RESPONSE ERROR] {phone}: {e}")
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[NO-RESPONSE SCHEDULER ERROR] {e}")
    asyncio.create_task(_no_response_scheduler())

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Serve static files (logo, etc.)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/conversations")
def conversations_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "conversations.html")


@app.get("/hub")
def hub_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "hub.html")


@app.get("/email-campaigns")
def email_campaigns_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "email_campaigns.html")


@app.get("/")
@app.head("/")
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

        # Detect language from agent's first message
        eng_chars = sum(1 for c in req.message if 'a' <= c.lower() <= 'z')
        is_eng_first = eng_chars > len(req.message.strip()) * 0.4

        if is_eng_first:
            system = ("You are a client contacting a real estate company in Jerusalem. "
                      "Write short and natural (1-2 sentences max). You MUST write ONLY in English.\n\n"
                      "Client types (random):\n"
                      "- 80%: Normal client looking in Jerusalem, answers immediately. Name/phone only when asked.\n"
                      "- 5%: Slightly hesitant once, then cooperates.\n"
                      "- 5%: Very difficult, needs convincing.\n"
                      "- 10%: Client looking OUTSIDE Jerusalem. Could be any city (Tel Aviv, Herzliya Pituach, Rishon LeZion, Netanya, Haifa, Raanana, Caesarea, etc.) with any budget that makes sense (e.g. 6M apartment in Rishon, 40M penthouse in Tel Aviv, 25M villa in Herzliya Pituach, 3.5M in Netanya). You genuinely want to buy there.\n\n"
                      "Rules: Answer only what's asked. Give name/phone only when explicitly requested. "
                      "Invent diverse names, phones, budgets, areas. ALWAYS respond in English only.\n\n"
                      "REALISTIC BUDGETS (use these!):\n"
                      "- Talbieh/Rehavia/German Colony/Mamilla: 6.5M-12M+ ILS for 4 rooms\n"
                      "- Baka/Old Katamon/Arnona/Beit HaKerem: 4.2M-5.8M ILS for 4 rooms\n"
                      "- Givat Masua/Kiryat Shmuel/Ramat Sharett/new Gilo: 3.2M-4.2M ILS for 4 rooms\n"
                      "- Neve Yaakov/Pisgat Zeev/Ramot/old Gilo: 2.3M-3M ILS for 4 rooms\n"
                      "- Outside Jerusalem (if you're that 10%% type): Tel Aviv 5M-50M, Herzliya Pituach 15M-45M, Rishon/Netanya/Haifa 3M-8M, Raanana 4M-10M\n"
                      "Pick a budget that matches the area you choose.")
            scenario = ("Pick a random scenario (be diverse!): young couple buying first apartment, "
                        "investor looking for rental yield, family upgrading to larger apartment, "
                        "someone relocating for work, retiree downsizing, someone who saw an ad online, "
                        "parent buying for a child, expat returning to Israel, foreign buyer for holidays. "
                        "Property types: apartment, penthouse, garden apartment, duplex, mini-penthouse, cottage, studio. "
                        "Respond to the agent's greeting in English naturally.")
        else:
            system = ("אתה לקוח שפונה לחברת נדל\"ן בירושלים. כתוב קצר וטבעי (משפט-שניים מקסימום).\n\n"
                      "סוג הלקוח שלך נקבע אקראית:\n"
                      "- 80%: לקוח רגיל שמחפש בירושלים. תקציב/אזור/חדרים - עונה מיד. שם וטלפון - רק כשמבקשים.\n"
                      "- 5%: מהסס קצת. פעם אחת שואל למה, אחרי הסבר - נותן.\n"
                      "- 5%: נוקשה מאד. צריך שכנוע רציני.\n"
                      "- 10%: לקוח עם תקציב גבוה מאד שמחפש מחוץ לירושלים! למשל: פנטהאוז בתל אביב ב-40 מיליון, וילה בהרצליה פיתוח ב-30 מיליון, נכס בקיסריה. יש לך כסף רציני ואתה רוצה נכס יוקרה באזורים האלה.\n\n"
                      "כללים: תענה רק למה ששואלים. שם וטלפון רק כשמבקשים במפורש. "
                      "תמציא שמות/טלפונים/תקציבים/אזורים מגוונים. תענה בעברית בלבד.\n\n"
                      "תקציבים ריאליסטיים (השתמש בזה!):\n"
                      "- טלביה/רחביה/מושבה גרמנית/ממילא: 6.5-12+ מיליון ל-4 חדרים\n"
                      "- בקעה/קטמון הישנה/ארנונה/בית הכרם: 4.2-5.8 מיליון ל-4 חדרים\n"
                      "- גבעת משואה/קרית שמואל/רמת שרת/גילה חדש: 3.2-4.2 מיליון ל-4 חדרים\n"
                      "- נווה יעקב/פסגת זאב/רמות/גילה ישן: 2.3-3 מיליון ל-4 חדרים\n"
                      "- תל אביב (יוקרה): 20-50+ מיליון לפנטהאוזים/וילות\n"
                      "- הרצליה פיתוח: 25-45 מיליון לוילות\n"
                      "תבחר תקציב שמתאים לאזור שבחרת.")
            scenario = ("תבחר תרחיש אקראי (תגוון!): זוג צעיר שקונה דירה ראשונה, "
                        "משקיע שמחפש תשואה, משפחה שמשדרגת לדירה גדולה יותר, "
                        "מישהו שעובר בגלל עבודה, גמלאי שמקטין דירה, מישהו שראה מודעה, "
                        "הורה שקונה לילד, עולה חדש, קונה מחו\"ל לנופש. "
                        "סוגי נכס מגוונים: דירה, פנטהאוז, דירת גן, דופלקס, מיני-פנטהאוז, קוטג', סטודיו. "
                        "תענה לסוכן בקצרה.")

        _train_sessions[sid] = {
            "messages": [{"role": "system", "content": system}],
            "client": client_ai,
        }
        # Agent's message is the greeting - add it then generate client response
        _train_sessions[sid]["messages"].append({"role": "user", "content": req.message})
        resp = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=_train_sessions[sid]["messages"] + [{"role": "system", "content": scenario}],
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

    # Language detection for reminder
    eng_chars = sum(1 for c in req.message if 'a' <= c.lower() <= 'z')
    is_eng = eng_chars > len(req.message.strip()) * 0.4
    if is_eng:
        reminder = ("CRITICAL LANGUAGE SWITCH: The agent is writing in ENGLISH. "
                    "From now on you MUST respond ONLY in English. You are now an English-speaking client. "
                    "Do NOT use any Hebrew words. Respond naturally as an English speaker. "
                    "If you previously spoke Hebrew, switch to English immediately — you are bilingual.")
    else:
        reminder = "תזכורת: תענה רק למה ששאלו. אם שאלו על הדירה - תענה על הדירה בלבד. אבל אם הסוכן מבקש פרטים ליצירת קשר (כמו 'תשאיר פרטים', 'תשאיר שם וטלפון', 'איך לחזור אליך', 'מה השם שלך', 'נחזור אליך') - תתן מיד שם וטלפון פיקטיביים. אם הסוכן ביקש פרטים ליצירת קשר יותר מפעם אחת - תבין שהוא צריך את זה ותתן שם וטלפון. אם הסוכן אומר שיחזור - תגיד 'בטח, אני דוד 053-7654321'. לא לסיים בלי להשאיר פרטים אם הסוכן ביקש."

    # Generate next client message
    resp = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages + [{"role": "system", "content": reminder}],
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
        # Don't delete session yet - /create-lead needs it
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
        return None  # לא מתעניין — נשמר ב-sessions בלבד
    if not convo.profile.phone:
        return None

    language = getattr(convo, "_language", "he")
    dry = not (sehel.PROJECT_ID or sehel.WEBHOOK_URL)
    try:
        payload = sehel.build_payload(
            convo.profile, level, score,
            language=language,
            media_source=media_source,
        )
        result = sehel.push_lead(payload, dry_run=dry)
    except Exception:
        return None

    _pushed.add(sid)
    return result.get("leadId") if not dry else "DRY_RUN"


# === Agent Bot Mode (bot as agent, user as client) ===
_agent_sessions: dict[str, Conversation] = {}


class AgentChatRequest(BaseModel):
    session_id: str | None = None
    message: str


@app.post("/agent-chat")
def agent_chat(req: AgentChatRequest) -> dict:
    """Bot as agent — uses the ReAct prompts."""
    if req.session_id and req.session_id in _agent_sessions:
        sid = req.session_id
    else:
        sid = str(uuid4())
        _agent_sessions[sid] = Conversation()

    convo = _agent_sessions[sid]
    turn, score = convo.send(req.message)
    return {
        "session_id": sid,
        "reply": turn.reply,
        "stage": turn.stage,
        "level": score.level,
        "score": score.score,
        "handoff_to_human": turn.handoff_to_human,
    }


@app.get("/agent")
def agent_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "agent.html")


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
    client_msgs = " ".join([m["content"] for m in messages if m.get("role") in ("assistant", "user")])

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
    budget_match2 = re.search(r'עד\s*\S*\s*(\d[\d,.]+)', client_msgs)
    if not profile.get("budget_ils") and budget_match2:
        profile["budget_ils"] = budget_match2.group(0)
    budget_match3 = re.search(r'תקציב[^\d]*(\d[\d,.]+\s*(?:מיליון|million|M)?)', client_msgs)
    if not profile.get("budget_ils") and budget_match3:
        profile["budget_ils"] = budget_match3.group(1)

    # חדרים
    rooms_match = re.search(r'(\d)\s*חדרים', client_msgs)
    if rooms_match:
        profile["rooms"] = rooms_match.group(1)
    rooms_match2 = re.search(r'(\d)\s*rooms|bedroom', client_msgs, re.IGNORECASE)
    if not profile.get("rooms") and rooms_match2:
        profile["rooms"] = rooms_match2.group(1)

    # אזור - חילוץ כל מיקום שמוזכר
    import re as re2
    area_patterns = [
        r'באזור\s+([\u05d0-\u05ea\s\-]+)',
        r'בשכונת\s+([\u05d0-\u05ea\s\-]+)',
        r'בשכונה\s+([\u05d0-\u05ea\s\-]+)',
        r'\u05d1([\u05d0-\u05ea]{3,}[\s\u05d0-\u05ea]*)',
        r'in\s+([A-Za-z\s\-]+?)(?:\s*,|\s*\.|\s*$|\s+area|\s+neighborhood)',
        r'area[:\s]+([A-Za-z\s\-]+)',
    ]
    areas_known = ['רחביה', 'ארנונה', 'בקעה', 'טלביה', 'מושבה גרמנית', 'מרכז העיר',
            'קטמון', 'נחלאות', 'גילו', 'עיר גנים', 'פסגת זאב',
            'בית הכרם', 'ממילא', 'ימין משה', 'רמות', 'נווה יעקב',
            'גבעת משואה', 'קרית שמואל', 'רמת שרת', 'בית וגן', 'קרית יובל',
            'תל אביב', 'הרצליה', 'נתניה', 'חיפה', 'רעננה', 'ראשון לציון',
            'German Colony', 'Rehavia', 'Talbiya', 'Arnona', 'Baka',
            'Beit HaKerem', 'Mamilla', 'Ramot', 'Neve Yaakov', 'Pisgat Zeev',
            'Tel Aviv', 'Herzliya', 'Netanya', 'Haifa', 'Raanana']
    # קודם כל תבדוק אזורים מוכרים
    for area in areas_known:
        if area.lower() in client_msgs.lower():
            profile["area"] = area
            break
    # אם לא נמצא - נסה לחלץ מהטקסט
    if not profile.get("area"):
        for pat in area_patterns:
            m = re2.search(pat, client_msgs)
            if m:
                extracted_area = m.group(1).strip().rstrip('.,!?')
                if len(extracted_area) >= 3 and extracted_area not in ['אני', 'שלום', 'היי']:
                    profile["area"] = extracted_area
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

    # תוספות (amenities)
    amenities = []
    amenity_keywords = {
        'מרפסת': ['מרפסת'],
        'מחסן': ['מחסן'],
        'חניה': ['חניה'],
        'ממד': ['ממד'],
        'מעלית': ['מעלית'],
        'גישה לנכים': ['גישה לנכים', 'נגישות'],
        'נוף': ['נוף'],
    }
    for amenity, keywords in amenity_keywords.items():
        if any(kw in client_msgs for kw in keywords):
            amenities.append(amenity)
    if amenities:
        import json as json_mod
        profile["amenities"] = json_mod.dumps(amenities, ensure_ascii=False)

    # קרבה ל (nearBy)
    nearby = []
    nearby_keywords = {
        'בית כנסת': ['בית כנסת', 'בתי כנסיות'],
        'סופרים': ['סופר', 'סופרים'],
        'מרכז': ['מרכז', 'קרוב למרכז'],
        'בית ספר': ['בית ספר', 'בתי ספר'],
        'תחבורה ציבורית': ['תחבורה', 'אוטובוס', 'רכבת'],
        'גני ילדים': ['גני ילדים', 'גן ילדים', 'מעון', 'גנים'],
        'פארק': ['פארק', 'גן ציבורי'],
        'שירותים': ['שירותים'],
    }
    for place, keywords in nearby_keywords.items():
        if any(kw in client_msgs for kw in keywords):
            nearby.append(place)
    # חילוץ חופשי - אם הלקוח אמר "קרבה ל" או "קרוב ל"
    import re as re3
    nearby_free = re3.findall(r'קרבה ל([\u05d0-\u05ea\s]+)', client_msgs)
    nearby_free += re3.findall(r'קרוב ל([\u05d0-\u05ea\s]+)', client_msgs)
    nearby_free += re3.findall(r'close to ([A-Za-z\s]+)', client_msgs, re3.IGNORECASE)
    nearby_free += re3.findall(r'near ([A-Za-z\s]+)', client_msgs, re3.IGNORECASE)
    for nf in nearby_free:
        cleaned = nf.strip().rstrip('.,!?')
        if cleaned and len(cleaned) >= 2 and cleaned not in nearby:
            nearby.append(cleaned)
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


@app.get("/calendar")
def calendar_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "calendar.html")


@app.get("/api/meetings")
def get_meetings(date: str | None = None, start: str | None = None, end: str | None = None, agent: str | None = None):
    from . import database as _db
    if start and end:
        meetings = _db.get_meetings_range(start, end, agent)
    else:
        meetings = _db.get_meetings(date, agent)
    return {"meetings": meetings}


@app.post("/api/meetings")
async def create_meeting(request: Request):
    from . import database as _db
    data = await request.json()
    mid = _db.create_meeting(
        agent_name=data.get("agent_name", ""),
        agent_email=data.get("agent_email", ""),
        client_name=data.get("client_name", ""),
        meeting_date=data.get("meeting_date", ""),
        meeting_time=data.get("meeting_time", ""),
        meeting_type=data.get("meeting_type", "frontal"),
        handled_by=data.get("handled_by", ""),
        zoom_link=data.get("zoom_link", ""),
        notes=data.get("notes", "")
    )
    return {"status": "ok", "id": mid}


@app.put("/api/meetings/{meeting_id}")
async def update_meeting(meeting_id: int, request: Request):
    from . import database as _db
    data = await request.json()
    conn = _db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE meetings SET client_name={_db.PH}, meeting_time={_db.PH}, meeting_type={_db.PH}, zoom_link={_db.PH}, notes={_db.PH} WHERE id={_db.PH}",
        (data.get('client_name',''), data.get('meeting_time',''), data.get('meeting_type','frontal'), data.get('zoom_link',''), data.get('notes',''), meeting_id)
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.delete("/api/meetings/{meeting_id}")
def delete_meeting(meeting_id: int):
    from . import database as _db
    _db.delete_meeting(meeting_id)
    return {"status": "ok"}


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
- 80% מהפעמים: לקוח רגיל שמחפש בירושלים. לא אכפת לו למסור פרטים. תקציב/אזור/חדרים - עונה מיד. שם וטלפון - נותן רק כשמבקשים במפורש.
- 5% מהפעמים: לקוח שמהסס קצת. פעם אחת אומר "למה אתה צריך את זה?" או "אני אשמח קודם לשמוע פרטים" אבל אחרי שהסוכן מסביר - נותן.
- 5% מהפעמים: לקוח מאד נוקשה. "אני לא משאיר פרטים לאף אחד" / "זה לא עניינך" / "תפסיק להתקשר" / "הדירות שלכם יקרות". צריך שכנוע מאד רציני.
- 10% מהפעמים: לקוח שמחפש מחוץ לירושלים! יכול להיות כל עיר וכל תקציב שמתאים. למשל: דירה בראשון לציון ב-6 מיליון, פנטהאוז בתל אביב ב-40 מיליון, וילה בהרצליה פיתוח ב-25 מיליון, דירה בנתניה ב-3.5 מיליון, דירה ברעננה ב-5 מיליון, דירה בחיפה ב-4 מיליון. אתה רוצה לקנות שם.

כללים קריטיים:
- תענה רק למה ששואלים אותך. אל תוסיף מידע שלא ביקשו.
- אם שואלים על הדירה (חדרים/אזור/תקציב) - תענה רק על הדירה. אל תוסיף שם וטלפון אם לא ביקשו.
- שם וטלפון תמסור רק כשהסוכן מבקש במפורש "תשאיר פרטים" או "מה השם שלך?" או "איך אפשר לחזור אליך?".
- תמציא שמות מגוונים, טלפונים מגוונים, תקציבים מגוונים, אזורים מגוונים.
- תרחישים מגוונים: קניה/שכירות/השקעה/מכירה.
- יכול להיות בעברית או באנגלית.

תקציבים ריאליסטיים:
- טלביה/רחביה/מושבה גרמנית/ממילא: 6.5-12+ מיליון ל-4 חדרים
- בקעה/קטמון הישנה/ארנונה/בית הכרם: 4.2-5.8 מיליון ל-4 חדרים
- גבעת משואה/קרית שמואל/רמת שרת/גילה חדש: 3.2-4.2 מיליון ל-4 חדרים
- נווה יעקב/פסגת זאב/רמות/גילה ישן: 2.3-3 מיליון ל-4 חדרים
- מחוץ לירושלים: תל אביב 5-50 מיליון, הרצליה פיתוח 15-45 מיליון, ראשון/נתניה/חיפה 3-8 מיליון, רעננה 4-10 מיליון
תבחר תקציב שמתאים לאזור שבחרת."""

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


@app.post("/api/admin/backfill-sehel")
async def backfill_sehel(request: Request):
    """חד-פעמי — שולח סיכום שיחה לשכל עבור רשימת טלפונים."""
    data = await request.json()
    secret = data.get("secret", "")
    if secret != "oren2024backfill":
        return {"error": "unauthorized"}
    phones = data.get("phones", [])
    results = []
    for phone in phones:
        record = db.get_reengagement_record(phone)
        if not record:
            results.append({"phone": phone, "status": "not_found"})
            continue
        transcript = record.get("transcript") or ""
        name = record.get("client_name") or ""
        summary = f"בוט וואטסאפ — ינון — {name}:\n{transcript}" if transcript else f"בוט וואטסאפ — ינון — {name}: לא ענה"
        try:
            result = sehel.log_call_summary(phone, summary)
            results.append({"phone": phone, "name": name, "status": "ok", "result": str(result)})
        except Exception as e:
            results.append({"phone": phone, "name": name, "status": "error", "reason": str(e)})
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
