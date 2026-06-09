"""ממשק דירוג לסוכנים — לב תקופת הדמו.

הסוכן קורא שיחה שלמה של הבוט ("דניאל") מול לקוח, ומדרג את רמת הרצינות
של הליד בצבע: 🔴 אדום / 🟠 כתום / 🟢 ירוק. הדירוג נשמר ל-sessions.json.

הרצה:  python -m app.review_cli <agent_id>
דוגמה: python -m app.review_cli agent_3
"""

import sys

from . import feedback


def _print_transcript(rec: feedback.SessionRecord) -> None:
    print("\n" + "=" * 64)
    for msg in rec.transcript:
        who = "👤 הלקוח" if msg["role"] == "user" else "💬 דניאל"
        print(f"{who}: {msg['content']}")
    print("-" * 64)
    print(f"   [הסיווג שהבוט חישב: {rec.bot_level} ({rec.bot_score})]")


def rate_one(rec: feedback.SessionRecord, agent_id: str) -> bool:
    """מחזיר False אם הסוכן ביקש לצאת, אחרת True."""
    _print_transcript(rec)
    choice = input(
        "דרג את רצינות הליד —  [r] 🔴 אדום  [o] 🟠 כתום  [g] 🟢 ירוק  "
        "[s] דילוג  [q] יציאה: "
    ).strip().lower()

    if choice == "q":
        return False
    if choice == "s":
        return True

    color_map = {"r": "red", "o": "orange", "g": "green"}
    if choice not in color_map:
        print("בחירה לא מוכרת — מדלג.")
        return True

    rec.agent_color = color_map[choice]
    rec.agent_id = agent_id
    rec.notes = input("הערה (אופציונלי — למשל למה דירגת ככה): ").strip()
    feedback.update(rec)

    emoji = feedback.COLOR_EMOJI[rec.agent_color]
    matched = "✓ תואם לבוט" if feedback.COLOR_TO_LEVEL[rec.agent_color] == rec.bot_level else "✗ שונה מהבוט"
    print(f"{emoji} נשמר. {matched}")
    return True


def main() -> None:
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "agent_unknown"
    pending = feedback.list_pending()
    if not pending:
        print("אין שיחות הממתינות לדירוג. הריצי שיחות ב-cli.py קודם.")
        return

    print(f"שלום {agent_id} — {len(pending)} שיחות ממתינות לדירוג.")
    for rec in pending:
        if not rate_one(rec, agent_id):
            break
    print("\nתודה! הדירוגים נשמרו. הריצי `python -m app.distill` כדי לעדכן את הבוט.")


if __name__ == "__main__":
    main()
