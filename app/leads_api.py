"""API endpoints למערכת הלידים."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from . import database as db

router = APIRouter(prefix="/api/leads", tags=["leads"])

# session_id -> Conversation (shared with main.py via import)
_inbound_sessions: dict = {}


class LoginRequest(BaseModel):
    name: str
    password: str


class SetPasswordRequest(BaseModel):
    name: str
    password: str


class LeadUpdate(BaseModel):
    rating: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    notes: Optional[str] = None


class AssignRequest(BaseModel):
    lead_id: int
    agent_id: int


# === Auth ===

@router.post("/login")
def login(req: LoginRequest):
    user = db.get_user(req.name, req.password)
    if not user:
        # בדיקה אם המשתמש קיים אבל בלי סיסמה (כניסה ראשונה)
        user_no_pass = db.get_user(req.name)
        if user_no_pass and user_no_pass["password"] is None:
            raise HTTPException(400, "needs_password")
        raise HTTPException(401, "שם או סיסמה לא נכונים")
    return {"user": {"id": user["id"], "name": user["name"], "role": user["role"]}}


@router.post("/check-user")
def check_user(req: dict):
    name = req.get("name", "")
    user = db.get_user(name)
    if not user:
        raise HTTPException(404, "משתמש לא נמצא")
    return {"has_password": user["password"] is not None, "role": user["role"]}


@router.post("/set-password")
def set_password(req: SetPasswordRequest):
    user = db.get_user(req.name)
    if not user:
        raise HTTPException(404, "משתמש לא נמצא")
    if user["password"] is not None:
        raise HTTPException(400, "כבר יש סיסמה")
    db.set_password(req.name, req.password)
    return {"status": "ok"}


# === Leads ===

@router.get("/all")
def get_all_leads():
    return db.get_all_leads()


@router.get("/agent/{agent_id}")
def get_agent_leads(agent_id: int):
    return db.get_leads_for_agent(agent_id)


@router.put("/{lead_id}")
def update_lead(lead_id: int, req: LeadUpdate):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    db.update_lead(lead_id, data)
    return {"status": "ok"}


@router.post("/assign")
def assign_lead(req: AssignRequest):
    db.update_lead(req.lead_id, {"assigned_to": req.agent_id, "status": "assigned"})
    return {"status": "ok"}


@router.delete("/{lead_id}")
def delete_lead(lead_id: int):
    db.delete_lead(lead_id)
    return {"status": "ok"}


# === Agents ===

@router.get("/agents")
def get_agents():
    return db.get_all_agents()


# === Inbound Lead (from CSV / CRM / WhatsApp batch) ===

class InboundLeadRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    source: str = "reengagement"  # reengagement / facebook / google / yad2
    first_message: Optional[str] = None  # הודעה ראשונה מותאמת אישית (אופציונלי)


class InboundLeadResponse(BaseModel):
    session_id: str
    greeting: str  # ההודעה שצריך לשלוח ללקוח ב-WhatsApp
    lead_id: int


@router.post("/inbound", response_model=InboundLeadResponse)
def inbound_lead(req: InboundLeadRequest) -> InboundLeadResponse:
    """
    מקבל ליד נכנס (מ-CSV / CRM / AWS batch) ומכין שיחה עם הבוט.

    הזרימה:
    1. שומר את הליד ב-DB
    2. פותח Conversation חדש עם הפרופיל הידוע
    3. מחזיר session_id + greeting לשליחה ב-WhatsApp

    תגובות הלקוח נכנסות אחר כך דרך POST /agent-chat עם אותו session_id.
    """
    from .engine import Conversation
    from .prompts import GREETING

    # 1. שמירה ב-DB
    lead_id = db.create_lead({
        "contact_name": req.name,
        "phone": req.phone,
        "intent": "unknown",
        "notes": f"source:{req.source}",
    })

    # 2. פתיחת שיחה עם פרופיל ידוע מראש
    convo = Conversation()
    if req.name:
        convo.profile.contact_name = req.name
    if req.phone:
        convo.profile.phone = req.phone

    # 3. בניית הודעת פתיחה
    if req.first_message:
        greeting = req.first_message
    elif req.name:
        greeting = f"שלום {req.name.split()[0]}, אני דניאל ממשרד אורן כהן גרופ. "\
                   "נשמח לעדכן אותך על נכסים חדשים שיכולים לעניין אותך. "\
                   "האם תרצה לשמוע פרטים?"
    else:
        greeting = GREETING

    sid = str(uuid4())
    _inbound_sessions[sid] = {"convo": convo, "lead_id": lead_id}

    return InboundLeadResponse(session_id=sid, greeting=greeting, lead_id=lead_id)


@router.post("/inbound/{session_id}/message")
def inbound_message(session_id: str, req: dict) -> dict:
    """
    מקבל תגובה נכנסת מהלקוח (Webhook מ-WhatsApp) וממשיך את השיחה.

    גוף הבקשה: { "message": "טקסט מהלקוח" }
    מחזיר: { "reply": "...", "stage": "...", "level": "...", "handoff": bool }
    """
    session = _inbound_sessions.get(session_id)
    if not session:
        raise HTTPException(404, "session not found")

    message = req.get("message", "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    convo = session["convo"]
    lead_id = session["lead_id"]

    turn, score = convo.send(message)

    # עדכון ה-DB עם מה שחולץ
    update_data = {}
    if convo.profile.contact_name:
        update_data["contact_name"] = convo.profile.contact_name
    if convo.profile.phone:
        update_data["phone"] = convo.profile.phone
    if convo.profile.budget_ils:
        update_data["budget"] = str(convo.profile.budget_ils)
    if convo.profile.area:
        update_data["area"] = convo.profile.area
    if convo.profile.rooms:
        update_data["rooms"] = str(convo.profile.rooms)
    if convo.profile.intent and convo.profile.intent != "unknown":
        update_data["intent"] = convo.profile.intent
    if convo.profile.timeline and convo.profile.timeline != "unknown":
        update_data["timeline"] = convo.profile.timeline
    if convo.profile.financing and convo.profile.financing != "unknown":
        update_data["financing"] = convo.profile.financing

    # דירוג לפי score
    rating_map = {"High": "hot", "Medium": "warm", "Low": "cold"}
    update_data["rating"] = rating_map.get(score.level, "none")
    update_data["status"] = "handoff" if turn.handoff_to_human else "in_progress"

    if update_data:
        db.update_lead(lead_id, update_data)

    # ניקוי session אם השיחה הסתיימה
    if turn.handoff_to_human:
        _inbound_sessions.pop(session_id, None)

    return {
        "reply": turn.reply,
        "stage": turn.stage,
        "level": score.level,
        "score": score.score,
        "handoff": turn.handoff_to_human,
        "lead_id": lead_id,
    }
