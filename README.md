# אורן כהן גרופ — בוט סיווג לידים

מנוע שיחה חכם לסיווג לידים נכנסים בנדל"ן יוקרה. הבוט מנהל דיאלוג מלווה,
מחלץ פרמטרים, ומסווג כל ליד ל-High / Medium / Low.

## ארכיטקטורה

```
לקוח → engine.Conversation.send()
          │
          ├─ Claude (Structured Outputs) → BotTurn {reply, stage, extracted, handoff}
          │     • reply: התשובה היוקרתית ללקוח
          │     • extracted: הנתונים שחולצו מהשיחה
          │
          ├─ _merge() → פרופיל מצטבר על פני כל התורות
          └─ scoring.score_lead() → LeadScore {score, level}  ← דטרמיניסטי, בקוד
```

**עיקרון מפתח:** ה-LLM אחראי על *ניסוח וחילוץ* בלבד. חישוב ה-Score נעשה בקוד
(`scoring.py`) — כך הסיווג יציב, שקוף, וקל לכיול בתקופת הדמו.

## קבצים

| קובץ | תפקיד |
|------|--------|
| `app/prompts.py` | ה-system prompt, הטון, ברכת הפתיחה, ודוגמאות-הזהב |
| `app/schemas.py` | מבני הנתונים (Pydantic) |
| `app/scoring.py` | לוגיקת הסיווג — משקלים וספים |
| `app/engine.py` | מנוע השיחה |
| `app/cli.py` | צ'אט טרמינל לבדיקה (רושם כל תור למאגר הביקורת) |
| `app/main.py` | שכבת FastAPI |
| `app/feedback.py` | מאגר השיחות — כל שיחה נשמרת לדירוג |
| `app/review_cli.py` | דירוג סוכן בסוף שיחה: 🔴 אדום / 🟠 כתום / 🟢 ירוק |
| `app/distill.py` | השוואת דירוג הסוכן לבוט (דיוק) + דוגמאות-זהב |
| `app/sehel.py` | אינטגרציה ל-CRM "שכל" — הזרקת לידים מסווגים |

## הרצה

```powershell
pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# בדיקה מהירה בטרמינל:
python -m app.cli

# או כשרת API:
uvicorn app.main:app --reload
```

## לולאת האימון (תקופת הדמו)

```
1. python -m app.cli                → שיחה מול 'דניאל'; בסיום נשמרת לדירוג
2. python -m app.review_cli agent_3 → הסוכן מדרג את הליד: 🔴 / 🟠 / 🟢
3. python -m app.distill            → דיוק (דירוג סוכן מול בוט) + דוגמאות-זהב
4. הבוט טוען את דוגמאות-הזהב אוטומטית בהרצה הבאה → הטון משתפר
```

הצבע של הסוכן הוא ה"אמת" האנושית: 🔴=Low · 🟠=Medium · 🟢=High.
distill משווה אותו לסיווג שהבוט חישב — כך מודדים דיוק ויודעים אם לכייל
את `scoring.py`. שיחות ירוקות הופכות לדוגמאות few-shot — ללא אימון מחדש.

## כיול הסיווג

המשקלים והספים ב-`scoring.py` הם נקודת פתיחה. כיילי אותם לפי הנתונים
האמיתיים שלכם בתקופת הדמו — זה בדיוק מה שמערכת הפידבק תייצר.

## אינטגרציית "שכל"

API ישיר: `POST https://leads.sehel.co.il` עם `project_id` בגוף הבקשה.
מוגדר ב-`app/sehel.py`. כל עוד `SEHEL_PROJECT_ID` ריק — רץ ב-**dry-run**
(לא שולח). תצוגה מקדימה של ה-payload: `python -m app.sehel`.
אפשר גם מסלול Make/Zapier ע"י הגדרת `SEHEL_WEBHOOK_URL`. ראה `.env.example`.

## הצעדים הבאים

1. ✅ ממשק פידבק לסוכנים (דירוג צבעים) — בוצע.
2. ✅ אינטגרציה ל"שכל" (API ישיר) — בוצע; ממתין ל-`project_id` מהתמיכה.
3. **חיבור WhatsApp** — WhatsApp Business API.
4. **התמדה** — להחליף את ה-session בזיכרון ב-Redis/DB.
