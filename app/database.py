"""מערכת לידים — Database (SQLite)."""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "leads.db"


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            password TEXT,
            role TEXT NOT NULL DEFAULT 'agent',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name TEXT,
            phone TEXT,
            budget TEXT,
            area TEXT,
            rooms TEXT,
            property_type TEXT,
            floor TEXT,
            financing TEXT,
            timeline TEXT,
            intent TEXT,
            rating TEXT DEFAULT 'none',
            status TEXT DEFAULT 'new',
            assigned_to INTEGER,
            transcript TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users(id)
        );
    """)

    # יצירת המנהל והסוכנים
    agents = ["אריה", "דב", "רבקה", "מוישי", "מיכאל", "אהרון", "ליסה"]
    
    # מנהל
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (name, password, role) VALUES (?, ?, ?)",
            ("מנהל", "1234", "manager")
        )
    except:
        pass

    # סוכנים (בלי סיסמה - יגדירו בכניסה ראשונה)
    for agent in agents:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO users (name, role) VALUES (?, ?)",
                (agent, "agent")
            )
        except:
            pass

    conn.commit()
    conn.close()


def get_user(name, password=None):
    conn = get_db()
    if password:
        user = conn.execute(
            "SELECT * FROM users WHERE name=? AND password=?", (name, password)
        ).fetchone()
    else:
        user = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    conn.close()
    return dict(user) if user else None


def set_password(name, password):
    conn = get_db()
    conn.execute("UPDATE users SET password=? WHERE name=?", (password, name))
    conn.commit()
    conn.close()


def get_all_agents():
    conn = get_db()
    agents = conn.execute("SELECT * FROM users WHERE role='agent'").fetchall()
    conn.close()
    return [dict(a) for a in agents]


def create_lead(data: dict) -> int:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute("""
        INSERT INTO leads (contact_name, phone, budget, area, rooms, property_type,
                          floor, financing, timeline, intent, transcript, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("contact_name"), data.get("phone"), data.get("budget"),
        data.get("area"), data.get("rooms"), data.get("property_type"),
        data.get("floor"), data.get("financing"), data.get("timeline"),
        data.get("intent"), json.dumps(data.get("transcript", []), ensure_ascii=False),
        data.get("notes", ""), now, now
    ))
    lead_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return lead_id


def get_all_leads():
    conn = get_db()
    leads = conn.execute("""
        SELECT l.*, u.name as agent_name
        FROM leads l
        LEFT JOIN users u ON l.assigned_to = u.id
        ORDER BY l.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(l) for l in leads]


def get_leads_for_agent(agent_id: int):
    conn = get_db()
    leads = conn.execute("""
        SELECT * FROM leads WHERE assigned_to=? ORDER BY created_at DESC
    """, (agent_id,)).fetchall()
    conn.close()
    return [dict(l) for l in leads]


def update_lead(lead_id: int, data: dict):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    sets = []
    vals = []
    for key, val in data.items():
        if key in ("rating", "status", "assigned_to", "notes", "contact_name", "phone",
                   "budget", "area", "rooms", "property_type", "floor", "financing", "timeline", "intent"):
            sets.append(f"{key}=?")
            vals.append(val)
    sets.append("updated_at=?")
    vals.append(now)
    vals.append(lead_id)
    conn.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_lead(lead_id: int):
    conn = get_db()
    conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()


# Initialize on import
init_db()
