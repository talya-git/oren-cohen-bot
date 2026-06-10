"""שכבת API (FastAPI) — לחיבור עתידי לוואטסאפ/אתר.

הרצה:  uvicorn app.main:app --reload
בשלב זה ניהול ה-session הוא בזיכרון (dict). בפרודקשן — Redis/DB.
"""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import sehel
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
