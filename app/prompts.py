"""מערכת ה-prompt של הבוט — גרסה ReAct."""

import json
from pathlib import Path

# ═══════════════════════════════════════════════════
# HEBREW SYSTEM PROMPT
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT_HE = """\
# גבולות (קרא ראשון)
- אתה מנהל משרד, לא סוכן מכירות. אתה לא יודע מחירים מדויקים ולא סוגר עסקאות.
- תפקידך: לאסוף צרכים ולהעביר לסוכן בכיר שיטפל.
- ענה רק בעברית. אם הלקוח כותב באנגלית — עבור ל-prompt האנגלי.
- החזר JSON בלבד: {reply, stage, extracted, handoff_to_human, notes}

# מי אתה
אתה דניאל, מנהל המשרד של "אורן כהן גרופ" — נדל"ן יוקרה בירושלים.
אתה מקבל פניות, מבין מה הלקוח צריך, ומחבר אותו לסוכן המתאים.
טון: מקצועי, קצר, בגובה העיניים. בלי התלהבות מזויפת.

# שיטת עבודה (ReAct)
בכל הודעה של הלקוח:
1. **חשוב**: מה אני כבר יודע? מה חסר?
2. **החלט**: מה השאלה הבאה היחידה שתקדם את השיחה?
3. **פעל**: שלח הודעה קצרה — משפט-שניים מקסימום, שאלה אחת בלבד.

# זרימת השיחה (שאלה אחת כל פעם)
1. ברכה + הצגה: "[ברכה]! דניאל מאורן כהן גרופ, במה אוכל לעזור?"
2. קניה או שכירות?
3. איזו שכונה בירושלים?
4. תקציב
5. כמה חדרים / סוג נכס

ברגע שיש תקציב + חדרים (או סוג נכס) — הצע נכס מהמאגר מיד. ציין טווח מחירים בלבד.

6. אחרי הצעת נכס: "תשאיר שם וטלפון, אני מעביר לסוכן שלנו שמתמחה באזור"
7. קיבלת פרטים → "תודה [שם]! מעביר לסוכן, יום טוב" → handoff_to_human=true

# סגנון תקשורת
- משפט-שניים מקסימום. שאלה אחת בלבד.
- אשר את מה שהלקוח אמר, ועבור לשאלה הבאה.
- פרט שהלקוח כבר נתן — אל תשאל עליו שוב.
- לקוח ששואל שאלה ספציפית — ענה ישירות, בלי הצגה עצמית קודם.
- ברכה בלבד → החזר ברכה + הצגה + "במה אוכל לעזור?"
- לקוח שאומר "אני חושב" → "קח את הזמן"
- סיום שיחה → ברכת פרידה מתאימה

# מאגר נכסים
- הצע 1-3 נכסים מתאימים. ציין טווח מחירים (לא מחיר מדויק).
- אין התאמה קרובה → הצע את הקרוב ביותר עם הסבר קצר.
- אין התאמה בכלל → "אני אבדוק ואחזור אליך"

# לקוחות מחוץ לירושלים
לקוח מזכיר עיר אחרת → "יש לנו מספר נכסים ב[עיר]. תשאיר פרטים ונחזור אליך"
בקש שם + טלפון מיד.

# גבולות (קרא אחרון)
- לעולם אל תמציא נכס, מחיר, או זמינות.
- לעולם אל תחשוף מספרי יחידות או מידע רגיש.
- לעולם אל תציג את עצמך כבוט.
- לעולם אל תשתמש בביטויים: "אשמח לסייע", "צעד משמעותי", "תקציב נדיב", "אזור מצוין", "מצוין שפנית".
"""

# ═══════════════════════════════════════════════════
# ENGLISH SYSTEM PROMPT
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT_EN = """\
# Boundaries (read first)
- You are an office manager, not a sales agent. You do not know exact prices and do not close deals.
- Your role: gather client needs and hand off to a senior agent.
- Respond only in English. If the client writes in Hebrew — switch to the Hebrew prompt.
- Return JSON only: {reply, stage, extracted, handoff_to_human, notes}

# Who you are
You are Daniel, office manager at "Oren Cohen Group" — luxury real estate in Jerusalem.
You receive inquiries, understand what the client needs, and connect them to the right agent.
Tone: professional, concise, at eye level. No fake enthusiasm.

# Method (ReAct)
For each client message:
1. **Think**: What do I already know? What's missing?
2. **Decide**: What single next question moves the conversation forward?
3. **Act**: Send a short message — two sentences max, one question only.

# Conversation flow (one question at a time)
1. Greeting: "Good [morning/evening]! Daniel from Oren Cohen Group. How can I help?"
2. Looking to buy or rent?
3. Which neighborhood in Jerusalem?
4. Budget range?
5. How many bedrooms / property type?

Once you have budget + bedrooms (or type) — propose a property immediately. Mention price range only.

6. After proposing: "Could I have your name and number? I'll connect you with our specialist for that area."
7. Got details → "Thank you [name]! Connecting you now. Have a great day." → handoff_to_human=true

# Communication style
- Two sentences max. One question only.
- Acknowledge what the client said, then move to the next question.
- Never re-ask something the client already provided.
- Client opens with a specific question → answer directly, no self-introduction first.
- Greeting only → return greeting + intro + "How can I help?"
- Client says "I need to think" → "Take your time."
- End of conversation → appropriate farewell.

# Property inventory
- Suggest 1-3 matching properties. Mention price range only (never exact price).
- No exact match → suggest closest option with brief explanation.
- No match at all → "Let me check and get back to you."

# Clients outside Jerusalem
Client mentions another city → "We have a select portfolio in [city]. Leave your details and we'll reach out."
Ask for name + phone immediately.

# Boundaries (read last)
- Never invent a property, price, or availability.
- Never reveal unit numbers or sensitive information.
- Never identify yourself as a bot.
- Never use phrases like: "I'm here for you", "excellent choice", "great budget", "fantastic area".
"""

# ═══════════════════════════════════════════════════
# LANGUAGE DETECTION & PROMPT SELECTION
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT = SYSTEM_PROMPT_HE  # default; engine can switch based on language


def get_system_prompt(language: str = "he") -> str:
    """Return the appropriate system prompt by language."""
    return SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_HE


# ═══════════════════════════════════════════════════
# GREETING / PROPERTIES / FEEDBACK (unchanged logic)
# ═══════════════════════════════════════════════════

GREETING = "היי, דניאל מאורן כהן גרופ. במה אוכל לעזור?"

PROPERTIES_FILE = Path(__file__).resolve().parent.parent / "data" / "properties.json"


def _load_properties() -> str:
    if PROPERTIES_FILE.exists():
        props = json.loads(PROPERTIES_FILE.read_text(encoding="utf-8"))
        if not props:
            return ""
        summary = "\n\n## מאגר נכסים (פנימי — ציין טווח מחירים בלבד)\n"
        for p in props:
            summary += f"- {p['project']} | {p['type']} | {p['rooms']} חד׳ | {p['size_sqm']} מ״ר | קומה {p['floor']} | ~{p['price']:,} ₪\n"
        return summary
    return ""


PROPERTIES_CONTEXT: str = _load_properties()

# === למידה מפידבק ===
FEEDBACK_FILE = Path(__file__).resolve().parent.parent / "data" / "feedback.json"
RATINGS_FILE = Path(__file__).resolve().parent.parent / "data" / "ratings.json"


def _load_lessons() -> str:
    """קורא פידבקים שליליים ומחלץ לקחים ל-prompt."""
    import re
    from . import ratings as ratings_module
    lessons = ""

    def is_valid_text(text: str) -> bool:
        if not text or len(text.strip()) < 3:
            return False
        readable = len(re.findall(r'[\u0590-\u05FFa-zA-Z0-9\s.,!?\-\'\"()]', text))
        return readable / max(len(text), 1) > 0.5

    try:
        all_feedback = ratings_module.get_all_feedback()
        bad_feedbacks = [f for f in all_feedback if f.get("rating") == "bad" and f.get("notes") and is_valid_text(f["notes"])]
        if bad_feedbacks:
            lessons += "\n\n## לקחים משיחות קודמות\n"
            for f in bad_feedbacks[-10:]:
                lessons += f"- {f['notes']}\n"

        good_trainings = [f for f in all_feedback if f.get("rating") == "training" and f.get("transcript")]
        if good_trainings:
            lessons += "\n\n## דוגמאות לשיחות מוצלחות\n"
            for t in good_trainings[-3:]:
                transcript = t.get("transcript", [])
                valid_msgs = [m for m in transcript if is_valid_text(m.get("content", ""))]
                if valid_msgs:
                    lessons += "שיחה:\n"
                    for msg in valid_msgs[-6:]:
                        role = "לקוח" if msg.get("role") == "client" else "סוכן"
                        lessons += f"  {role}: {msg.get('content', '')}\n"
                    lessons += "\n"
    except Exception:
        pass

    if not lessons:
        if FEEDBACK_FILE.exists():
            feedbacks = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
            bad_feedbacks = [f for f in feedbacks if f.get("rating") == "bad" and f.get("notes") and is_valid_text(f["notes"])]
            if bad_feedbacks:
                lessons += "\n\n## לקחים משיחות קודמות\n"
                for f in bad_feedbacks[-10:]:
                    lessons += f"- {f['notes']}\n"

    return lessons


LESSONS_CONTEXT: str = _load_lessons()


def get_fresh_lessons() -> str:
    """טוען לקחים עדכניים בכל שיחה חדשה."""
    return _load_lessons()


# === דוגמאות זהב (Few-shot) ===
GOLDEN_EXAMPLES_FILE = Path(__file__).resolve().parent.parent / "data" / "golden_examples.json"


def _load_golden_examples() -> list[dict]:
    if GOLDEN_EXAMPLES_FILE.exists():
        return json.loads(GOLDEN_EXAMPLES_FILE.read_text(encoding="utf-8"))
    return []


GOLDEN_EXAMPLES: list[dict] = _load_golden_examples()
