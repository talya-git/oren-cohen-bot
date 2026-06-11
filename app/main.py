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

app = FastAPI(title="Oren Cohen Group — Lead Bot")

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
    if req.session_id and req.session_id in _sessions:
        sid, convo = req.session_id, _sessions[req.session_id]
    else:
        sid = str(uuid4())
        convo = _sessions[sid] = Conversation()

    turn, score = convo.send(req.message)

    # הזרקה לשכל פעם אחת — כשהליד בשל (handoff או High) ויש טלפון
    lead_id = _maybe_push_to_sehel(sid, convo, score.level, score.score, req.media_source, turn.handoff_to_human)

    return ChatResponse(
        session_id=sid,
        reply=turn.reply,
        stage=turn.stage,
        level=score.level,
        score=score.score,
        handoff_to_human=turn.handoff_to_human,
        sehel_lead_id=lead_id,
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
    system = """אתה לקוח שמתעניין בנדל"ן יוקרה בירושלים. אתה פונה לחברת אורן כהן גרופ.
תתנהג כמו לקוח אמיתי — שאל שאלות טבעיות, תגיב כאדם.
אתה יכול להיות: משקיע מחו"ל, קונה ישראלי, מחפש שכירות, מתעניין בפרויקט ספציפי, וכו'.
פתח עם הודעה ראשונה קצרה וטבעית כלקוח. יכול להיות בעברית או באנגלית.
אל תהיה ארוך — משפט-שניים מקסימום בכל הודעה."""

    messages = [{"role": "system", "content": system}]
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.9
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
        messages=messages + [{"role": "system", "content": "אם השיחה הגיעה לסיום טבעי (הסוכן אמר שיחזור, הלקוח אמר תודה/ביי, או שכל הפרטים נאספו) — תגיד 'תודה רבה, יום טוב!' ותסיים. אחרת תמשיך לשאול כלקוח."}],
        temperature=0.9
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
        return {"done": True}

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
