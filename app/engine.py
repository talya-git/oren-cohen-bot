"""מנוע השיחה — חיבור ל-OpenAI GPT API עם חילוץ פרמטרים וסיווג."""

import json
import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from .prompts import GOLDEN_EXAMPLES, SYSTEM_PROMPT
from .schemas import BotTurn, ExtractedParams
from .scoring import score_lead, LeadScore

load_dotenv()

# Groq API (compatible with OpenAI SDK)
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    http_client=httpx.Client(verify=False),
)
MODEL = "llama-3.3-70b-versatile"


class Conversation:
    def __init__(self):
        self.profile = ExtractedParams()
        self.messages: list[dict] = []

        # בניית system instruction עם דוגמאות זהב
        system = SYSTEM_PROMPT
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
                reply=raw,
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

    def _merge(self, extracted: ExtractedParams) -> None:
        """מיזוג — ערכים חדשים דורסים null/unknown בלבד."""
        for field in extracted.model_fields:
            new_val = getattr(extracted, field)
            if new_val is None or new_val == "unknown":
                continue
            setattr(self.profile, field, new_val)
