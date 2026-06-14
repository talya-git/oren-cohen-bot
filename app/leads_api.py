"""API endpoints למערכת הלידים."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from . import database as db

router = APIRouter(prefix="/api/leads", tags=["leads"])


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
