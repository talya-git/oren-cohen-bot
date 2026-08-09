"""מנוע השיחה — חיבור ל-OpenAI GPT API עם חילוץ פרמטרים וסיווג."""

import json
import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from .prompts import GOLDEN_EXAMPLES, PROPERTIES_CONTEXT, get_fresh_lessons, get_system_prompt
from .schemas import BotTurn, ExtractedParams
from .scoring import score_lead, LeadScore

load_dotenv()

# OpenAI API
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=httpx.Client(verify=False, timeout=60.0),
)

MODEL = "gpt-4o"


class Conversation:
    def __init__(self, language: str = "he", project_name: str | None = None):
        self.profile = ExtractedParams()
        self.messages: list[dict] = []
        self._language = language
        self._project_name = project_name  # שם הפרויקט מהשכל (לזכירה ללקוח)
        self._system_built = False

    @classmethod
    def from_session(cls, session: dict) -> "Conversation":
        """טוען שיחה קיימת מ-session record."""
        convo = cls()
        convo.profile = ExtractedParams(**(session.get("profile") or {}))
        convo._system_built = True  # מונע בניית system כפולה

        # בנה system prompt + הנחיה לזרימת המשך
        system = get_system_prompt("he")
        if PROPERTIES_CONTEXT:
            system += PROPERTIES_CONTEXT
        fresh_lessons = get_fresh_lessons()
        if fresh_lessons:
            system += fresh_lessons
        system += (
            "\n\n--- Output format ---\n"
            "Return valid JSON only: {reply, stage, extracted, handoff_to_human, notes}\n"
            "extracted fields: budget_ils, timeline, financing, intent, "
            "has_property_to_sell, area, city, neighborhood, property_type, rooms, engagement, contact_name, phone.\n"
            "city: עיר מבוקשת. neighborhood: שכונה ספציפית. property_type: דירה/פנטאוז/דירת גן/וילה/דופלקס etc.\n"
            "Unknown fields \u2192 null or \"unknown\". No text outside the JSON.\n"
        )
        system += (
            "\n\n## זרימת שיחת המשך (חשוב!)\n"
            "זוהי שיחת המשך עם ליד קיים. הפתיחה שלך חייבת להיות:\n"
            "\"היי, זה דניאל מאורן כהן גרופ. ראיתי שבעבר התעניינת בקניית דירה בירושלים — זה עדיין רלוונטי עבורך?\"\n"
            "אם הלקוח מאשר עניין — שאל: \"תזכיר לי, באיזה אזור דיברנו? או שכרגע כבר לא משנה לך אזור?\"\n"
            "לאחר מכן המשך לפי סדר השאלות הרגיל: חדרים, דרישות, לוח זמנים, תקציב (אחרון), פרטי קשר.\n"
            "אל תסכם את השיחה הקודמת ואל תציין מה כבר ידוע — שאל מחדש בצורה טבעית.\n"
        )
        convo.messages.append({"role": "system", "content": system})
        return convo

    def _build_system(self, language: str) -> str:
        """Build system prompt with context for the detected language."""
        system = get_system_prompt(language)
        if PROPERTIES_CONTEXT:
            system += PROPERTIES_CONTEXT
        fresh_lessons = get_fresh_lessons()
        if fresh_lessons:
            system += fresh_lessons
        if GOLDEN_EXAMPLES:
            system += "\n\n## דוגמאות מאושרות (few-shot)\n"
            for ex in GOLDEN_EXAMPLES[:5]:
                system += f"\nלקוח: {ex.get('user','')}\nדניאל: {ex.get('assistant','')}\n"
        if self._project_name:
            if language == "en":
                system += (
                    f"\n\n## Previous Interest\n"
                    f"This client previously inquired about the '{self._project_name}' project. "
                    f"If they ask what they were interested in, remind them: "
                    f"'You previously showed interest in the {self._project_name} project. "
                    f"We still have a few apartments available there — would you like to hear more about it, "
                    f"or are you open to exploring our other projects as well?'"
                )
            else:
                system += (
                    f"\n\n## עניין קודם\n"
                    f"הלקוח התעניין בעבר בפרויקט '{self._project_name}'. "
                    f"אם הלקוח שואל על מה התעניין, הזכר לו: "
                    f"'בעבר התעניינת בפרויקט {self._project_name}. "
                    f"נשארו לנו עוד כמה דירות שם — תרצה לחזור לשמוע על הפרויקט הזה או שאתה זורם על עוד פרויקטים שלנו?'"
                )
        else:
            if language == "en":
                system += (
                    "\n\n## Previous Interest\n"
                    "This client previously inquired about buying a property in Jerusalem. "
                    "If they ask what they were interested in, say: "
                    "'You previously showed interest in buying a property in Jerusalem. "
                    "Is that still relevant for you?'"
                )
            else:
                system += (
                    "\n\n## עניין קודם\n"
                    "הלקוח התעניין בעבר ברכישת נכס בירושלים. "
                    "אם הלקוח שואל על מה התעניין, אמור: "
                    "'בעבר התעניינת ברכישת נכס בירושלים. האם זה עדיין רלוונטי עבורך?'"
                )
        system += (
            "\n\n--- Output format ---\n"
            "Return valid JSON only: {reply, stage, extracted, handoff_to_human, notes}\n"
            "extracted fields: budget_ils, timeline, financing, intent, "
            "has_property_to_sell, area, city, neighborhood, property_type, rooms, engagement, contact_name, phone.\n"
            "city: עיר מבוקשת. neighborhood: שכונה ספציפית. property_type: דירה/פנטאוז/דירת גן/וילה/דופלקס etc.\n"
            "Unknown fields \u2192 null or \"unknown\". No text outside the JSON.\n"
        )
        return system

    @staticmethod
    def _is_english(text: str) -> bool:
        eng_chars = sum(1 for c in text if 'a' <= c.lower() <= 'z')
        return eng_chars > len(text.strip()) * 0.4

    def send(self, user_message: str) -> tuple[BotTurn, LeadScore]:
        # Detect language and build system prompt on first message
        if not self._system_built:
            self._language = "en" if self._is_english(user_message) else "he"
            system = self._build_system(self._language)
            self.messages.insert(0, {"role": "system", "content": system})
            self._system_built = True

        self.messages.append({"role": "user", "content": user_message})

        # זיהוי מפורש של "לא מעוניין" — סגירת שיחה מיידית
        not_interested = [
            "לא רלוונטי", "לא מעוניין", "לא מתעניין", "לא צריך", "לא רוצה",
            "לא כרגע", "לא עכשיו", "לא עכש",
            "not interested", "not relevant", "no thanks", "no thank you", "not now", "not at the moment",
            "לא תודה", "לא, תודה", "לא מעניין"
        ]
        if any(p in user_message.lower() for p in not_interested):
            closing = "תודה על העדכון! אם בעתיד תתעניין, אשמח לעמוד לרשותך 😊"
            if self._language == "en":
                closing = "Thank you for letting me know! If you're ever interested in the future, feel free to reach out 😊"
            turn = BotTurn(
                reply=closing, stage="handoff",
                extracted=ExtractedParams(), handoff_to_human=True, notes="not_interested"
            )
            self.messages.append({"role": "assistant", "content": closing})
            return turn, score_lead(self.profile)

        response = client.chat.completions.create(
            model=MODEL,
            messages=self.messages,
            temperature=0.7,
        )

        raw = response.choices[0].message.content.strip()
        print(f"[DEBUG RAW] {raw[:200]}")

        # חילוץ JSON מתוך התשובה (גם אם יש טקסט מסביב)
        json_str = self._extract_json(raw)
        print(f"[DEBUG JSON] {json_str[:200]}")

        try:
            data = json.loads(json_str)
            # תיקונים לנתונים שהמודל מחזיר
            if data.get("notes") is None:
                data["notes"] = ""
            if data.get("stage") is None:
                data["stage"] = "engagement"
            if data.get("handoff_to_human") is None:
                data["handoff_to_human"] = False
            if data.get("extracted") is None:
                data["extracted"] = {}
            # תיקון extracted - המודל לפעמים מחזיר עברית במקום אנגלית
            ext = data.get("extracted", {})
            intent_map = {"קנייה": "buy", "מכירה": "sell", "השקעה": "invest", "מתעניין": "browsing", "inquiry": "browsing"}
            if ext.get("intent") in intent_map:
                ext["intent"] = intent_map[ext["intent"]]
            elif ext.get("intent") not in (None, "buy", "sell", "invest", "browsing", "unknown"):
                ext["intent"] = "unknown"
            timeline_map = {"מיידי": "immediate"}
            if ext.get("timeline") in timeline_map:
                ext["timeline"] = timeline_map[ext["timeline"]]
            elif ext.get("timeline") not in (None, "immediate", "3_months", "6_12_months", "exploring", "unknown"):
                ext["timeline"] = "unknown"
            if ext.get("financing") not in (None, "cash", "mortgage_approved", "mortgage_needed", "unknown"):
                ext["financing"] = "unknown"
            if ext.get("engagement") not in (None, "high", "medium", "low"):
                ext["engagement"] = "medium"
            # תיקון שדות שהמודל מחזיר כ-"unknown" אבל צריכים להיות None
            if ext.get("budget_ils") == "unknown" or ext.get("budget_ils") == "null":
                ext["budget_ils"] = None
            if ext.get("rooms") == "unknown" or ext.get("rooms") == "null":
                ext["rooms"] = None
            if isinstance(ext.get("budget_ils"), str):
                # ניסיון להמיר מחרוזת מספרית
                try:
                    ext["budget_ils"] = int(ext["budget_ils"].replace(",", ""))
                except (ValueError, AttributeError):
                    ext["budget_ils"] = None
            if isinstance(ext.get("rooms"), str):
                try:
                    ext["rooms"] = int(ext["rooms"])
                except (ValueError, AttributeError):
                    ext["rooms"] = None
            data["extracted"] = ext
            # תיקון stage - המודל לפעמים מחזיר ערכים שלא ברשימה
            valid_stages = ("greeting", "intent", "qualification", "engagement", "cta", "handoff")
            if data.get("stage") not in valid_stages:
                data["stage"] = "engagement"
            turn = BotTurn(**data)
        except (json.JSONDecodeError, Exception):
            # fallback — חילוץ הטקסט שלפני ה-JSON כתשובה
            # try to extract just the reply field from the raw JSON even if full parse failed
            import re as _re
            reply_match = _re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            if reply_match:
                clean_reply = reply_match.group(1).replace('\\n', '\n').replace('\\"', '"')
            else:
                clean_reply = raw.split("{")[0].strip() if "{" in raw else raw
                clean_reply = clean_reply.split("```")[0].strip()
            if not clean_reply:
                clean_reply = "כן יש לנו מגוון נכסים, תוכל למקד אותי קצת מה אתה מחפש?"
            turn = BotTurn(
                reply=clean_reply,
                stage="engagement",
                extracted=ExtractedParams(),
                handoff_to_human=False,
                notes="parse_error",
            )

        # מיזוג הפרמטרים שחולצו לפרופיל מצטבר
        self._merge(turn.extracted)
        score = score_lead(self.profile)

        self.messages.append({"role": "assistant", "content": raw})

        return turn, score

    @staticmethod
    def _extract_json(text: str) -> str:
        """חילוץ JSON מתוך טקסט שעשוי להכיל גם טקסט רגיל."""
        # ניקוי code fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("{"):
                    text = stripped
                    break
        # אם יש טקסט לפני ה-JSON, נחלץ רק את ה-JSON
        start = text.find("{")
        if start != -1:
            # מוצאים את הסוגר התואם
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i+1]
        return text

    def _merge(self, extracted: ExtractedParams) -> None:
        """מיזוג — ערכים חדשים דורסים null/unknown בלבד."""
        for field in extracted.model_fields:
            new_val = getattr(extracted, field)
            if new_val is None or new_val == "unknown":
                continue
            setattr(self.profile, field, new_val)
