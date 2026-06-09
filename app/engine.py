"""מנוע השיחה — חיבור ל-Gemini API עם חילוץ פרמטרים וסיווג."""

import json
import os
import ssl

import httpx
from dotenv import load_dotenv
from google import genai

from .prompts import GOLDEN_EXAMPLES, SYSTEM_PROMPT
from .schemas import BotTurn, ExtractedParams
from .scoring import score_lead, LeadScore

load_dotenv()

# Bypass SSL verification for corporate networks
client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY"),
    http_options={"api_version": "v1beta", "headers": {}},
)
# Patch the internal httpx client to skip SSL
client._api_client._httpx_client = httpx.Client(verify=False)
MODEL = "gemini-2.0-flash"


class Conversation:
    def __init__(self):
        self.profile = ExtractedParams()
        self.history: list[dict] = []

        # בניית system instruction עם דוגמאות זהב
        system = SYSTEM_PROMPT
        if GOLDEN_EXAMPLES:
            system += "\n\n## דוגמאות מאושרות (few-shot)\n"
            for ex in GOLDEN_EXAMPLES[:5]:
                system += f"\nלקוח: {ex.get('user','')}\nדניאל: {ex.get('assistant','')}\n"

        self.chat = client.chats.create(
            model=MODEL,
            config={"system_instruction": system},
        )

    def send(self, user_message: str) -> tuple[BotTurn, LeadScore]:
        prompt = (
            f"{user_message}\n\n"
            "--- הנחיות מערכת פנימיות (לא מוצגות ללקוח) ---\n"
            "החזר JSON תקני בלבד עם השדות: reply, stage, extracted, handoff_to_human, notes.\n"
            "extracted חייב לכלול: budget_ils, timeline, financing, intent, "
            "has_property_to_sell, area, rooms, engagement, contact_name, phone.\n"
            "אם פרט לא ידוע השאר null או unknown.\n"
            "אל תוסיף טקסט מחוץ ל-JSON."
        )

        response = self.chat.send_message(prompt)
        raw = response.text.strip()

        # ניקוי markdown code fences אם קיימים
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        try:
            data = json.loads(raw)
            turn = BotTurn(**data)
        except (json.JSONDecodeError, Exception):
            # fallback — המודל לא החזיר JSON תקין
            turn = BotTurn(
                reply=response.text,
                stage="engagement",
                extracted=ExtractedParams(),
                handoff_to_human=False,
                notes="parse_error",
            )

        # מיזוג הפרמטרים שחולצו לפרופיל מצטבר
        self._merge(turn.extracted)
        score = score_lead(self.profile)

        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": turn.reply})

        return turn, score

    def _merge(self, extracted: ExtractedParams) -> None:
        """מיזוג — ערכים חדשים דורסים null/unknown בלבד."""
        for field in extracted.model_fields:
            new_val = getattr(extracted, field)
            if new_val is None or new_val == "unknown":
                continue
            setattr(self.profile, field, new_val)
