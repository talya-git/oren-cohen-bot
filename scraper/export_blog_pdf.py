"""PDF מסודר — כל פוסט: כותרת + תמונה + מלל מלא + קישור."""

import sys, json, io, os, urllib.request, requests
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Image, Spacer, HRFlowable, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

sys.stdout.reconfigure(encoding="utf-8")

FONT_PATH = "scraper/NotoSansHebrew.ttf"
if not os.path.exists(FONT_PATH):
    print("מוריד פונט...")
    urllib.request.urlretrieve(
        "https://github.com/google/fonts/raw/main/ofl/notosanshebrew/NotoSansHebrew%5Bwdth%2Cwght%5D.ttf",
        FONT_PATH
    )
pdfmetrics.registerFont(TTFont("Heb", FONT_PATH))

HEADERS = {"User-Agent": "Mozilla/5.0"}
IMG_W, IMG_H = 7*cm, 5*cm

def b(t): return get_display(str(t))

def fetch_img(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=8, verify=False)
        r.raise_for_status()
        data = io.BytesIO(r.content)
        # קרא מידות מקוריות לשמירת יחס
        from PIL import Image as PILImage
        pil = PILImage.open(io.BytesIO(r.content))
        orig_w, orig_h = pil.size
        ratio = orig_h / orig_w
        w = IMG_W
        h = min(w * ratio, 8*cm)  # מקסימום גובה 8cm
        img = Image(data, width=w, height=h)
        img.hAlign = "RIGHT"
        return img
    except Exception:
        return Spacer(1, 0.1*cm)

S_MAIN_TITLE = ParagraphStyle("mt", fontName="Heb", fontSize=22, alignment=TA_CENTER,
                               textColor=colors.HexColor("#8B6914"), spaceAfter=4)
S_MAIN_SUB   = ParagraphStyle("ms", fontName="Heb", fontSize=10, alignment=TA_CENTER,
                               textColor=colors.grey, spaceAfter=16)
S_TITLE = ParagraphStyle("t", fontName="Heb", fontSize=12, alignment=TA_RIGHT,
                          textColor=colors.HexColor("#5a3e00"), spaceAfter=6, leading=18)
S_BODY  = ParagraphStyle("b", fontName="Heb", fontSize=9, alignment=TA_RIGHT,
                          leading=15, spaceAfter=2)
S_LINK  = ParagraphStyle("l", fontName="Heb", fontSize=7.5, alignment=TA_LEFT,
                          textColor=colors.HexColor("#1a6496"), spaceAfter=4)


def build_pdf(posts, out_path):
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            rightMargin=1.8*cm, leftMargin=1.8*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = [
        Paragraph(b("שישי של פעם — ירושלים"), S_MAIN_TITLE),
        Paragraph(b(f"סה״כ {len(posts)} פוסטים | orencohengroup.com"), S_MAIN_SUB),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#8B6914")),
        Spacer(1, 0.6*cm),
    ]

    for i, p in enumerate(posts, 1):
        print(f"\r{i}/{len(posts)} — {p['title'][:55]}", end="", flush=True)

        block = []
        # כותרת
        block.append(Paragraph(b(f"{i}. {p['title']}"), S_TITLE))
        # תמונה
        if p.get("image"):
            block.append(fetch_img(p["image"]))
            block.append(Spacer(1, 0.2*cm))
        # תוכן
        for line in p.get("content", "").splitlines():
            line = line.strip()
            if line:
                block.append(Paragraph(b(line), S_BODY))
        # קישור
        block.append(Paragraph(p["link"], S_LINK))
        block.append(HRFlowable(width="100%", thickness=0.4,
                                 color=colors.HexColor("#D0C0A0")))
        block.append(Spacer(1, 0.4*cm))

        # KeepTogether רק על הכותרת + תמונה (לא כל הבלוק)
        story.append(KeepTogether(block[:3]))
        story.extend(block[3:])

    print()
    doc.build(story)
    print(f"✅ נשמר: {out_path}")


if __name__ == "__main__":
    src = "scraper/blog_posts_full.json"
    if not os.path.exists(src):
        src = "scraper/blog_posts.json"
    with open(src, encoding="utf-8") as f:
        posts = json.load(f)
    build_pdf(posts, "scraper/shishi_shel_paam.pdf")
