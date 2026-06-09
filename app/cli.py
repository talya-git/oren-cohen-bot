"""צ'אט טרמינל לבדיקה מהירה של המנוע.

הרצה:  python -m app.cli
דרוש:  משתנה סביבה ANTHROPIC_API_KEY

בסיום השיחה (יציאה) — השיחה כולה נשמרת למאגר הדירוג, כדי שסוכן
יוכל לדרג את רמת הליד בצבע ב-review_cli.py.
"""

from . import feedback, prompts
from .engine import Conversation
from .scoring import score_lead


def main() -> None:
    convo = Conversation()
    print("=" * 60)
    print("אורן כהן גרופ — דניאל (בוט סיווג לידים, דמו טרמינל)")
    print("הקלד 'יציאה' כדי לסיים ולשמור את השיחה לדירוג.")
    print("=" * 60)
    print(f"\n💬 דניאל: {prompts.GREETING}\n")

    # ברכת הפתיחה היא חלק מהשיחה — נשמרת ב-transcript לדירוג
    transcript: list[dict] = [{"role": "assistant", "content": prompts.GREETING}]

    while True:
        try:
            user = input("👤 ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user in ("יציאה", "exit", "quit"):
            break
        if not user:
            continue

        turn, score = convo.send(user)
        print(f"\n💬 דניאל: {turn.reply}\n")

        transcript.append({"role": "user", "content": user})
        transcript.append({"role": "assistant", "content": turn.reply})

        # תצוגת דיבאג — מה שיוזרק ל'שכל' מאחורי הקלעים
        flag = "  ⚠️ העברה לסוכן אנושי" if turn.handoff_to_human else ""
        print(f"   [stage={turn.stage} | {score.level} ({score.score})]{flag}\n")

    # שמירת השיחה כולה לדירוג (רק אם התקיים דיאלוג אמיתי)
    if len(transcript) > 1:
        final = score_lead(convo.profile)
        feedback.save_session(
            transcript=transcript,
            bot_level=final.level,
            bot_score=final.score,
            profile=convo.profile.model_dump(),
        )
        print(f"\n💾 השיחה נשמרה לדירוג (סיווג הבוט: {final.level}).")
        print("   סוכן יכול לדרג אותה: python -m app.review_cli <agent_id>")


if __name__ == "__main__":
    main()
