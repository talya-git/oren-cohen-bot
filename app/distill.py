"""זיקוק הפידבק — סוגר את לולאת האימון.

קורא את כל השיחות המדורגות ועושה שני דברים:
1. משווה את דירוג הצבע של הסוכן (האמת) לסיווג שהבוט חישב → מדדי דיוק
   + מטריצת בלבול, שמראים אם והיכן צריך לכייל את scoring.py.
2. מפיק דוגמאות-זהב מהשיחות שדורגו 🟢 ירוק — דוגמאות לטיפול מצוין בליד רציני.
   הדוגמאות נשמרות ל-data/golden_examples.json, ו-prompts.py טוען אותן אוטומטית.

הרצה:  python -m app.distill
"""

import json

from . import feedback
from .prompts import GOLDEN_EXAMPLES_FILE


def compute_metrics(sessions: list[feedback.SessionRecord]) -> dict:
    rated = [s for s in sessions if s.agent_color is not None]
    if not rated:
        return {"rated": 0}

    # מטריצת בלבול: מה הבוט חישב מול מה שהסוכן דירג
    levels = ["High", "Medium", "Low"]
    confusion = {bot: {agent: 0 for agent in levels} for bot in levels}
    agree = 0
    for s in rated:
        agent_level = feedback.COLOR_TO_LEVEL[s.agent_color]
        confusion[s.bot_level][agent_level] += 1
        if s.bot_level == agent_level:
            agree += 1

    return {
        "rated": len(rated),
        "accuracy": round(agree / len(rated), 2),
        "confusion_bot_vs_agent": confusion,
    }


def _flatten_to_pairs(transcript: list[dict]) -> list[dict]:
    """ממיר שיחה לזוגות (פניית לקוח → תשובת דניאל) עבור few-shot."""
    pairs = []
    for i in range(len(transcript) - 1):
        if transcript[i]["role"] == "user" and transcript[i + 1]["role"] == "assistant":
            pairs.append(
                {"user": transcript[i]["content"], "reply": transcript[i + 1]["content"]}
            )
    return pairs


def build_golden(sessions: list[feedback.SessionRecord]) -> list[dict]:
    golden = []
    for s in sessions:
        if s.agent_color == "green":  # ליד רציני שטופל היטב
            golden.extend(_flatten_to_pairs(s.transcript))
    return golden


def main() -> None:
    sessions = feedback.load_all()

    metrics = compute_metrics(sessions)
    print("=== מדדי דמו ===")
    print(f"  שיחות שדורגו: {metrics.get('rated', 0)}")
    if metrics.get("rated"):
        print(f"  דיוק הסיווג (בוט מול סוכן): {metrics['accuracy']}")
        print("  מטריצת בלבול (שורה=בוט, עמודה=סוכן):")
        for bot_level, row in metrics["confusion_bot_vs_agent"].items():
            print(f"    {bot_level:>6}: {row}")

    golden = build_golden(sessions)
    GOLDEN_EXAMPLES_FILE.parent.mkdir(exist_ok=True)
    GOLDEN_EXAMPLES_FILE.write_text(
        json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ נוצרו {len(golden)} דוגמאות-זהב (משיחות ירוקות) → {GOLDEN_EXAMPLES_FILE}")
    print("  הבוט יטען אותן אוטומטית בהרצה הבאה.")


if __name__ == "__main__":
    main()
