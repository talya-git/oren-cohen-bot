"""מערכת ה-prompt של הבוט — טוען פרומפטים מקבצים נפרדים."""

import json
from pathlib import Path

# ═══════════════════════════════════════════════════
# LOAD PROMPTS FROM SEPARATE FILES
# ═══════════════════════════════════════════════════

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

SYSTEM_PROMPT_HE = (_PROMPTS_DIR / "prompt_he.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT_EN = (_PROMPTS_DIR / "prompt_en.txt").read_text(encoding="utf-8")
SYSTEM_PROMPT = SYSTEM_PROMPT_HE  # default


def get_system_prompt(language: str = "he") -> str:
    """Return the appropriate system prompt by language."""
    return SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_HE


# ═══════════════════════════════════════════════════
# GREETING / PROPERTIES / FEEDBACK
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
