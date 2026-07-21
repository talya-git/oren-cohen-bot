"""שליחת מיילים דרך Mailjet API."""

import os
import urllib.request
import urllib.error
import json
import base64

MAILJET_API_KEY = os.getenv("MAILJET_API_KEY", "")
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "orencohengroup2020@gmail.com")
FROM_NAME = "בוט אורן כהן גרופ"


def send_report(to_email: str, agent_label: str, leads: list[dict]) -> None:
    subject = f"דוח הערת לידים שלך — {agent_label}"

    rows = ""
    for l in leads:
        sent_icon = "✅" if l.get("sent") else "❌"
        replied_icon = "✅" if l.get("replied") else "❌"
        transcript = (l.get("transcript") or "").strip() or "—"
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

    payload = json.dumps({
        "Messages": [{
            "From": {"Email": FROM_EMAIL, "Name": FROM_NAME},
            "To": [{"Email": to_email}],
            "Subject": subject,
            "HTMLPart": html,
        }]
    }).encode()

    credentials = base64.b64encode(f"{MAILJET_API_KEY}:{MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[MAILJET ERROR] {e.code}: {body}")
        raise
