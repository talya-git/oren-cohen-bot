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
        # הוסף עמודות חדשות אם לא קיימות
        for col, definition in [
            ("stalled_pushed", "BOOLEAN DEFAULT FALSE"),
            ("handoff", "BOOLEAN DEFAULT FALSE"),
        ]:
            try:
                cur.execute(f"ALTER TABLE reengagement_sent ADD COLUMN IF NOT EXISTS {col} {definition}")
                conn.commit()
            except Exception:
                conn.rollback()

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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reengagement_batches (
                id SERIAL PRIMARY KEY,
                agent_email TEXT NOT NULL,
                agent_label TEXT,
                report_sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reengagement_sent (
                id SERIAL PRIMARY KEY,
                batch_id INTEGER REFERENCES reengagement_batches(id),
                phone TEXT NOT NULL,
                client_name TEXT,
                agent_email TEXT NOT NULL,
                replied BOOLEAN DEFAULT FALSE,
                transcript TEXT,
                error TEXT DEFAULT '',
                read_at TIMESTAMPTZ,
                stalled_pushed BOOLEAN DEFAULT FALSE,
                sent_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id SERIAL PRIMARY KEY,
                agent_name TEXT NOT NULL,
                agent_email TEXT,
                client_name TEXT NOT NULL,
                meeting_date TEXT NOT NULL,
                meeting_time TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
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
            CREATE TABLE IF NOT EXISTS reengagement_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_email TEXT NOT NULL,
                agent_label TEXT,
                report_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reengagement_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER REFERENCES reengagement_batches(id),
                phone TEXT NOT NULL,
                client_name TEXT,
                agent_email TEXT NOT NULL,
                replied INTEGER DEFAULT 0,
                transcript TEXT,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                agent_email TEXT,
                client_name TEXT NOT NULL,
                meeting_date TEXT NOT NULL,
                meeting_time TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        ("בועז", None, "agent"),
        ("נתנאל", None, "agent"),
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


def ensure_agent(name: str):
    """מוסיף סוכן אם לא קיים."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            f"INSERT INTO users (name, role) VALUES ({PH},{PH}) ON CONFLICT (name) DO NOTHING"
            if DATABASE_URL else
            f"INSERT OR IGNORE INTO users (name, role) VALUES ({PH},{PH})",
            (name, "agent")
        )
        conn.commit()
    except Exception:
        pass
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


def is_conversation_done(phone: str) -> bool:
    return False  # בזיכרון בלבד — ראה _wa_done ב-whatsapp.py


def create_reengagement_batch(agent_email: str, agent_label: str) -> int:
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if DATABASE_URL:
        cur.execute(
            "INSERT INTO reengagement_batches (agent_email, agent_label, created_at) VALUES (%s,%s,%s) RETURNING id",
            (agent_email, agent_label, now)
        )
        batch_id = cur.fetchone()[0]
    else:
        cur.execute(
            "INSERT INTO reengagement_batches (agent_email, agent_label, created_at) VALUES (?,?,?)",
            (agent_email, agent_label, now)
        )
        batch_id = cur.lastrowid
    conn.commit()
    conn.close()
    return batch_id


def get_pending_batches() -> list:
    """מחזיר batches שעברו 24 שעות ועדיין לא נשלח להם דוח."""
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            SELECT * FROM reengagement_batches
            WHERE report_sent = FALSE
            AND created_at < NOW() - INTERVAL '24 hours'
        """)
    else:
        cur.execute("""
            SELECT * FROM reengagement_batches
            WHERE report_sent = 0
            AND created_at < datetime('now', '-24 hours')
        """)
    rows = _fetchall(cur)
    conn.close()
    return rows


def mark_batch_report_sent(batch_id: int) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"UPDATE reengagement_batches SET report_sent={PH} WHERE id={PH}", (True if DATABASE_URL else 1, batch_id))
    conn.commit()
    conn.close()


def get_batch_leads(batch_id: int) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM reengagement_sent WHERE batch_id={PH}", (batch_id,))
    rows = _fetchall(cur)
    conn.close()
    return rows


def mark_reengagement_sent(phone: str, client_name: str, agent_email: str, batch_id: int | None = None, error: str = "", transcript: str = "") -> None:
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if DATABASE_URL:
        cur.execute(
            "INSERT INTO reengagement_sent (phone, client_name, agent_email, batch_id, sent_at, transcript) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (phone, client_name, agent_email, batch_id, now, transcript)
        )
    else:
        cur.execute(
            "INSERT OR IGNORE INTO reengagement_sent (phone, client_name, agent_email, batch_id, sent_at, transcript) VALUES (?,?,?,?,?,?)",
            (phone, client_name, agent_email, batch_id, now, transcript)
        )
    conn.commit()
    conn.close()


def update_reengagement_replied(phone: str, replied: bool, transcript: str = "") -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE reengagement_sent SET replied={PH}, transcript={PH} WHERE phone={PH}",
        (replied, transcript, phone)
    )
    conn.commit()
    conn.close()


def mark_reengagement_handoff(phone: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE reengagement_sent SET handoff={PH} WHERE phone={PH}",
        (True if DATABASE_URL else 1, phone)
    )
    conn.commit()
    conn.close()


def get_sent_phones_set(phone: str) -> bool:
    """בודק אם מספר ספציפי כבר קיבל הודעה."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT 1 FROM reengagement_sent WHERE phone={PH} LIMIT 1", (phone,))
    exists = _fetchone(cur) is not None
    conn.close()
    return exists


def get_sent_phones(agent_email: str) -> set:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT phone FROM reengagement_sent WHERE agent_email={PH}", (agent_email,))
    phones = {row["phone"] for row in _fetchall(cur)}
    conn.close()
    return phones


def get_reengagement_record(phone: str) -> dict | None:
    """מחזיר רשומת reengagement לפי טלפון."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM reengagement_sent WHERE phone={PH} LIMIT 1", (phone,))
    row = _fetchone(cur)
    conn.close()
    return row


_POSITIVE_SIGNALS = ["כן", "yes", "מעוניין", "interested", "רלוונטי", "relevant", "בטח", "sure", "אשמח", "glad", "כמובן", "of course", "יאללה", "אוקי"]
_NEGATIVE_SIGNALS = ["no thanks", "not interested", "not relevant", "לא רלוונטי", "לא מעוניין", "לא רלוונט", "לא צריך", "לא רוצה", "הסר", "remove", "stop", "unsubscribe"]
_HANDOFF_SIGNALS = ["יום טוב", "להתראות", "bye", "thank you", "תודה רבה"]


def _is_positive_conversation(transcript: str) -> bool:
    """בודק שהלקוח ענה חיובי לפחות פעם אחת ולא שללי בהמשך."""
    if not transcript:
        return False
    found_positive = False
    for line in transcript.split("\n"):
        if not (line.startswith("לקוח:") or line.startswith("Client:")):
            continue
        line_lower = line.lower()
        # אם יש סיגנל שלילי בשורה זו — דלג אותה
        if any(sig in line_lower for sig in _NEGATIVE_SIGNALS):
            continue
        if any(sig in line_lower for sig in _POSITIVE_SIGNALS):
            found_positive = True
    return found_positive


def get_stalled_conversations(hours: int = 2) -> list:
    """מחזיר שיחות שהלקוח ענה חיובי אבל לא סיים — לא הועברו לסוכן ולא נשלחו לשכל."""
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = TRUE
            AND stalled_pushed = FALSE
            AND sent_at < NOW() - INTERVAL '%s hours'
            AND (transcript NOT LIKE '%%יום טוב%%'
                 AND transcript NOT LIKE '%%להתראות%%'
                 AND transcript NOT LIKE '%%bye%%'
                 AND transcript NOT LIKE '%%thank you%%')
        """, (hours,))
    else:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = 1
            AND stalled_pushed = 0
            AND sent_at < datetime('now', ? || ' hours')
            AND (transcript NOT LIKE '%יום טוב%'
                 AND transcript NOT LIKE '%להתראות%'
                 AND transcript NOT LIKE '%bye%'
                 AND transcript NOT LIKE '%thank you%')
        """, (f"-{hours}",))
    rows = _fetchall(cur)
    conn.close()
    # סנן רק שיחות שבהן הלקוח ענה חיובי לפחות פעם אחת
    return [r for r in rows if _is_positive_conversation(r.get("transcript", ""))]


def mark_stalled_pushed(phone: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE reengagement_sent SET stalled_pushed={PH} WHERE phone={PH}",
        (True if DATABASE_URL else 1, phone)
    )
    conn.commit()
    conn.close()


def get_no_response_conversations(hours: int = 24) -> list:
    """מחזיר שיחות שלא ענו בכלל אחרי X שעות ועדיין לא עודכנו."""
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = FALSE
            AND stalled_pushed = FALSE
            AND sent_at < NOW() - INTERVAL '%s hours'
        """, (hours,))
    else:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = 0
            AND stalled_pushed = 0
            AND sent_at < datetime('now', ? || ' hours')
        """, (f"-{hours}",))
    rows = _fetchall(cur)
    conn.close()
    return rows


def get_no_response_conversations(hours: int = 24) -> list:
    """מחזיר שיחות שלא ענו בכלל אחרי X שעות ועדיין לא עודכנו בשכל."""
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = FALSE
            AND stalled_pushed = FALSE
            AND sent_at < NOW() - INTERVAL '%s hours'
        """, (hours,))
    else:
        cur.execute("""
            SELECT * FROM reengagement_sent
            WHERE replied = 0
            AND stalled_pushed = 0
            AND sent_at < datetime('now', ? || ' hours')
        """, (f"-{hours}",))
    rows = _fetchall(cur)
    conn.close()
    return rows


def create_meeting(agent_name: str, agent_email: str, client_name: str, meeting_date: str, meeting_time: str, notes: str = "") -> int:
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if DATABASE_URL:
        cur.execute(
            "INSERT INTO meetings (agent_name, agent_email, client_name, meeting_date, meeting_time, notes, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (agent_name, agent_email, client_name, meeting_date, meeting_time, notes, now)
        )
        mid = cur.fetchone()[0]
    else:
        cur.execute(
            "INSERT INTO meetings (agent_name, agent_email, client_name, meeting_date, meeting_time, notes, created_at) VALUES (?,?,?,?,?,?,?)",
            (agent_name, agent_email, client_name, meeting_date, meeting_time, notes, now)
        )
        mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def get_meetings(date: str, agent_name: str | None = None) -> list:
    conn = get_db()
    cur = conn.cursor()
    if agent_name:
        cur.execute(f"SELECT * FROM meetings WHERE meeting_date={PH} AND agent_name={PH} ORDER BY meeting_time", (date, agent_name))
    else:
        cur.execute(f"SELECT * FROM meetings WHERE meeting_date={PH} ORDER BY agent_name, meeting_time", (date,))
    rows = _fetchall(cur)
    conn.close()
    return rows


def get_meetings_range(start: str, end: str, agent_name: str | None = None) -> list:
    conn = get_db()
    cur = conn.cursor()
    if agent_name:
        cur.execute(f"SELECT * FROM meetings WHERE meeting_date>={PH} AND meeting_date<={PH} AND agent_name={PH} ORDER BY meeting_date, meeting_time", (start, end, agent_name))
    else:
        cur.execute(f"SELECT * FROM meetings WHERE meeting_date>={PH} AND meeting_date<={PH} ORDER BY meeting_date, agent_name, meeting_time", (start, end))
    rows = _fetchall(cur)
    conn.close()
    return rows


def delete_meeting(meeting_id: int) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM meetings WHERE id={PH}", (meeting_id,))
    conn.commit()
    conn.close()


def get_reengagement_results(agent_email: str) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM reengagement_sent WHERE agent_email={PH} ORDER BY sent_at DESC",
        (agent_email,)
    )
    results = _fetchall(cur)
    conn.close()
    return results


# Initialize on import
init_db()
