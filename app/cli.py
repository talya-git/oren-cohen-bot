"""צ'אט טרמינל לבדיקה מהירה של המנוע.

הרצה:  python -m app.cli
דרוש:  משתנה סביבה ANTHROPIC_API_KEY

בסיום השיחה (יציאה) — השיחה כולה נשמרת למאגר הדירוג, כדי שסוכן
יוכל לדרג את רמת הליד בצבע ב-review_cli.py.
"""

import sys

from . import feedback, prompts
from .engine import Conversation
from .scoring import score_lead


def main() -> None:
    session_id = None
    args = sys.argv[1:]
    if "--session" in args:
        idx = args.index("--session")
        if idx + 1 < len(args):
            session_id = args[idx + 1]

    convo = Conversation()
    transcript: list[dict] = []

    if session_id:
        all_sessions = feedback._load_raw()
        match = next((s for s in all_sessions if s["id"].startswith(session_id)), None)
        if not match:
            print(f"Session '{session_id}' לא נמצא.")
            return
        convo = Conversation.from_session(match)
        transcript = list(match.get("transcript", []))
        print("=" * 60)
        print(f"ממשיך שיחה קיימת | {match['id'][:8]} | {match['bot_level']}")
        print("=" * 60)
        opening = "היי, זה דניאל מאורן כהן גרופ. ראיתי שבעבר התעניינת בקניית דירה בירושלים — זה עדיין רלוונטי עבורך?"
        print(f"\n💬 דניאל: {opening}\n")
        transcript = [{"role": "assistant", "content": opening}]
    else:
        print("=" * 60)
        print("אורן כהן גרופ — דניאל (בוט סיווג לידים, דמו טרמינל)")
        print("הקלד 'יציאה' כדי לסיים ולשמור את השיחה לדירוג.")
        print("=" * 60)
        print(f"\n💬 דניאל: {prompts.GREETING}\n")
        transcript = [{"role": "assistant", "content": prompts.GREETING}]

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
