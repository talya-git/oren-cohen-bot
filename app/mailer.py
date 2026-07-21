"""שליחת מיילים דרך Gmail SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_USER = os.getenv("GMAIL_USER", "office@orencohengroup.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")


def send_report(to_email: str, agent_label: str, leads: list[dict]) -> None:
    """
    שולח דוח הערת לידים לסוכן.
    leads: [{ name, phone, sent, replied, transcript, sent_at }]
    """
    subject = f"דוח הערת לידים שלך — {agent_label}"

    rows = ""
    for l in leads:
        sent_icon = "✅" if l.get("sent") else "❌"
        replied_icon = "✅" if l.get("replied") else "❌"
        transcript = (l.get("transcript") or "").strip() or "—"
        # חיתוך תמליל ארוך
        if len(transcript) > 800:
            transcript = transcript[:800] + "..."
        transcript_html = transcript.replace("\n", "<br>")
        rows += f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;">{l.get('name') or '—'}</td>
          <td style="padding:8px;border:1px solid #ddd;">{l.get('phone') or '—'}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">{sent_icon}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">{replied_icon}</td>
          <td style="padding:8px;border:1px solid #ddd;font-size:12px;direction:rtl;">{transcript_html}</td>
        </tr>"""

    html = f"""
    <html><body dir="rtl" style="font-family:Arial,sans-serif;font-size:14px;">
      <h2>דוח הערת לידים — {agent_label}</h2>
      <p>להלן סיכום הלידים שנשלחו אליהם הודעת WhatsApp:</p>
      <table style="border-collapse:collapse;width:100%;">
        <thead>
          <tr style="background:#f0f0f0;">
            <th style="padding:8px;border:1px solid #ddd;">שם</th>
            <th style="padding:8px;border:1px solid #ddd;">טלפון</th>
            <th style="padding:8px;border:1px solid #ddd;">נשלח</th>
            <th style="padding:8px;border:1px solid #ddd;">ענה</th>
            <th style="padding:8px;border:1px solid #ddd;">תמליל שיחה</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_USER, to_email, msg.as_string())
