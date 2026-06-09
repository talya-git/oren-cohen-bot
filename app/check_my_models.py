import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# הגדרה פשוטה ללא גרסאות API מיוחדות
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

print("מחפש מודלים זמינים בחשבון שלך...")
try:
    for m in client.models.list():
        print(f"שם מודל: {m.name}")
except Exception as e:
    print(f"קרתה שגיאה בחיבור: {e}")