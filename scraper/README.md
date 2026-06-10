# Sehel CRM Scraper

סקריפט אוטומטי שנכנס לשכל, מייצא מלאי פרויקטים ויד 2, ומעדכן את הבוט.

## התקנה (פעם אחת)

```bash
pip install playwright openpyxl
playwright install chromium
```

## הרצה

```bash
python scraper/scrape_sehel.py
```

הסקריפט:
1. מתחבר לשכל עם שם משתמש וסיסמא
2. נכנס ל"מלאי פרויקטים" ומייצא כל עמוד לאקסל
3. חוזר ונכנס ל"מלאי יד 2" ומייצא כל עמוד
4. מעדכן את `data/properties.json`

## הרצה אוטומטית כל חצי שעה (Windows)

צרי Task Scheduler:
1. פתחי Task Scheduler
2. Create Basic Task
3. Trigger: Daily, Repeat every 30 minutes
4. Action: Start a program
   - Program: python
   - Arguments: scraper/scrape_sehel.py
   - Start in: C:\Users\...\oren-cohen-bot

## הערות
- הסקריפט רץ עם חלון דפדפן (headless=False) כדי לראות מה קורה
- לריצה בלי חלון: שני ל-headless=True בקוד
- אם ה-selectors לא עובדים — צריך להתאים לממשק של שכל
