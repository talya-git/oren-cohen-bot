"""מנוע השיחה — חיבור ל-OpenAI GPT API עם חילוץ פרמטרים וסיווג."""

import json
import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from .prompts import GOLDEN_EXAMPLES, SYSTEM_PROMPT, PROPERTIES_CONTEXT
from .schemas import BotTurn, ExtractedParams
from .scoring import score_lead, LeadScore

load_dotenv()

# OpenAI API
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=httpx.Client(verify=False),
)
MODEL = "gpt-4o-mini"


class Conversation:
    def __init__(self):
        self.profile = ExtractedParams()
        self.messages: list[dict] = []

        # בניית system instruction עם דוגמאות זהב ומאגר נכסים
        system = SYSTEM_PROMPT
        if PROPERTIES_CONTEXT:
            system += PROPERTIES_CONTEXT
        if GOLDEN_EXAMPLES:
            system += "\n\n## דוגמאות מאושרות (few-shot)\n"
            for ex in GOLDEN_EXAMPLES[:5]:
                system += f"\nלקוח: {ex.get('user','')}\nדניאל: {ex.get('assistant','')}\n"

        system += (
            "\n\n--- הנחיות פלט ---\n"
            "החזר JSON תקני בלבד עם השדות: reply, stage, extracted, handoff_to_human, notes.\n"
            "extracted חייב לכלול: budget_ils, timeline, financing, intent, "
            "has_property_to_sell, area, rooms, engagement, contact_name, phone.\n"
            "אם פרט לא ידוע השאר null או unknown.\n"
            "אל תוסיף טקסט מחוץ ל-JSON."
        )

        self.messages.append({"role": "system", "content": system})

    def send(self, user_message: str) -> tuple[BotTurn, LeadScore]:
        self.messages.append({"role": "user", "content": user_message})

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
            data["extracted"] = ext
            # תיקון stage - המודל לפעמים מחזיר ערכים שלא ברשימה
            valid_stages = ("greeting", "intent", "qualification", "engagement", "cta", "handoff")
            if data.get("stage") not in valid_stages:
                data["stage"] = "engagement"
            turn = BotTurn(**data)
        except (json.JSONDecodeError, Exception):
            # fallback — חילוץ הטקסט שלפני ה-JSON כתשובה
            clean_reply = raw.split("{")[0].strip() if "{" in raw else raw
            clean_reply = clean_reply.split("```")[0].strip()
            if not clean_reply:
                clean_reply = "מה אוכל לעזור לך?"
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
