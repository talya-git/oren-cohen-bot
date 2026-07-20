"""מערכת לידים — Database (PostgreSQL / SQLite fallback)."""

import json
import os
from datetime import datetime, timezone

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip() or None

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        return conn

    def _fetchall(cursor):
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def _fetchone(cursor):
        if cursor.description is None:
            return None
        cols = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None

    PH = "%s"  # PostgreSQL placeholder

else:
    import sqlite3
    from pathlib import Path

    DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "leads.db"

    def get_db():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _fetchall(cursor):
        return [dict(r) for r in cursor.fetchall()]

    def _fetchone(cursor):
        row = cursor.fetchone()
        return dict(row) if row else None

    PH = "?"  # SQLite placeholder


def init_db():
    conn = get_db()
    cur = conn.cursor()

    if DATABASE_URL:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                password TEXT,
                role TEXT NOT NULL DEFAULT 'agent',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
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
                assigned_to INTEGER REFERENCES users(id),
                transcript TEXT,
                notes TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    else:
        cur.executescript("""
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

    # יצירת משתמשים ברירת מחדל
    for name, password, role in [
        ("מנהל", "1234", "manager"),
        ("אריה", None, "agent"),
        ("דב", None, "agent"),
        ("רבקה", None, "agent"),
        ("מוישי", None, "agent"),
        ("מיכאל", None, "agent"),
        ("אהרון", None, "agent"),
        ("ליסה", None, "agent"),
    ]:
        try:
            cur.execute(
                f"INSERT INTO users (name, password, role) VALUES ({PH},{PH},{PH}) ON CONFLICT (name) DO NOTHING"
                if DATABASE_URL else
                f"INSERT OR IGNORE INTO users (name, password, role) VALUES ({PH},{PH},{PH})",
                (name, password, role)
            )
        except Exception:
            pass

    conn.commit()
    conn.close()


def get_user(name, password=None):
    conn = get_db()
    cur = conn.cursor()
    if password:
        cur.execute(f"SELECT * FROM users WHERE name={PH} AND password={PH}", (name, password))
    else:
        cur.execute(f"SELECT * FROM users WHERE name={PH}", (name,))
    user = _fetchone(cur)
    conn.close()
    return user


def set_password(name, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET password={PH} WHERE name={PH}", (password, name))
    conn.commit()
    conn.close()


def get_all_agents():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE role='agent'")
    agents = _fetchall(cur)
    conn.close()
    return agents


def create_lead(data: dict) -> int:
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if DATABASE_URL:
        cur.execute("""
            INSERT INTO leads (contact_name, phone, budget, area, rooms, property_type,
                              floor, financing, timeline, intent, transcript, notes, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (
            data.get("contact_name"), data.get("phone"), data.get("budget"),
            data.get("area"), data.get("rooms"), data.get("property_type"),
            data.get("floor"), data.get("financing"), data.get("timeline"),
            data.get("intent"), json.dumps(data.get("transcript", []), ensure_ascii=False),
            data.get("notes", ""), now, now
        ))
        lead_id = cur.fetchone()[0]
    else:
        cur.execute("""
            INSERT INTO leads (contact_name, phone, budget, area, rooms, property_type,
                              floor, financing, timeline, intent, transcript, notes, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("contact_name"), data.get("phone"), data.get("budget"),
            data.get("area"), data.get("rooms"), data.get("property_type"),
            data.get("floor"), data.get("financing"), data.get("timeline"),
            data.get("intent"), json.dumps(data.get("transcript", []), ensure_ascii=False),
            data.get("notes", ""), now, now
        ))
        lead_id = cur.lastrowid
    conn.commit()
    conn.close()
    return lead_id


def get_all_leads():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT l.*, u.name as agent_name
        FROM leads l
        LEFT JOIN users u ON l.assigned_to = u.id
        ORDER BY l.created_at DESC
    """)
    leads = _fetchall(cur)
    conn.close()
    return leads


def get_leads_for_agent(agent_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM leads WHERE assigned_to={PH} ORDER BY created_at DESC", (agent_id,))
    leads = _fetchall(cur)
    conn.close()
    return leads


def update_lead(lead_id: int, data: dict):
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    allowed = {"rating", "status", "assigned_to", "notes", "contact_name", "phone",
               "budget", "area", "rooms", "property_type", "floor", "financing", "timeline", "intent"}
    sets = []
    vals = []
    for key, val in data.items():
        if key in allowed:
            sets.append(f"{key}={PH}")
            vals.append(val)
    sets.append(f"updated_at={PH}")
    vals.append(now)
    vals.append(lead_id)
    cur.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id={PH}", vals)
    conn.commit()
    conn.close()


def delete_lead(lead_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM leads WHERE id={PH}", (lead_id,))
    conn.commit()
    conn.close()


# Initialize on import
init_db()
