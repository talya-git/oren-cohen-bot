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


ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "naomi@orencohengroup.com")
ADMIN_EMAIL2 = "lisa@orencohengroup.com"


def send_report(to_email: str, agent_label: str, leads: list[dict]) -> None:
    import io
    import openpyxl

    subject = f"דוח הערת לידים שלך — {agent_label}"

    # בניית HTML
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

    # בניית אקסל
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "לידים"
    ws.append(["שם", "טלפון", "נשלח", "ענה", "תמליל שיחה"])
    for l in leads:
        transcript = (l.get("transcript") or "").strip()
        if len(transcript) > 2000:
            transcript = transcript[:2000] + "..."
        ws.append([
            l.get("name") or "",
            l.get("phone") or "",
            "כן" if l.get("sent") else "לא",
            "כן" if l.get("replied") else "לא",
            transcript,
        ])
    excel_buf = io.BytesIO()
    wb.save(excel_buf)
    excel_b64 = base64.b64encode(excel_buf.getvalue()).decode()

    to_list = [{"Email": to_email}]
    if ADMIN_EMAIL and ADMIN_EMAIL != to_email:
        to_list.append({"Email": ADMIN_EMAIL})
    if ADMIN_EMAIL2 and ADMIN_EMAIL2 != to_email and ADMIN_EMAIL2 != ADMIN_EMAIL:
        to_list.append({"Email": ADMIN_EMAIL2})

    payload = json.dumps({
        "Messages": [{
            "From": {"Email": FROM_EMAIL, "Name": FROM_NAME},
            "To": to_list,
            "Subject": subject,
            "HTMLPart": html,
            "Attachments": [{
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Filename": f"leads_{agent_label}.xlsx",
                "Base64Content": excel_b64,
            }],
        }]
    }).encode()

    credentials = base64.b64encode(f"{MAILJET_API_KEY}:{MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=payload,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(f"[REPORT] sent to {[t['Email'] for t in to_list]} | response={body[:200]}")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[MAILJET ERROR] {e.code}: {body}")
        raise


def send_agent_lead_alert(agent_email: str, client_name: str, client_phone: str, transcript: str) -> None:
    """שולח מייל התראה לסוכן על ליד מתעניין."""
    subject = f"🔔 התראה מהבוט — ליד מתעניין"
    html = (
        "<html><body dir='rtl' style='font-family:Arial,sans-serif;font-size:14px;'>"
        "<h2 style='color:#16a34a;'>🔔 ליד מתעניין מהבוט!</h2>"
        "<table style='border-collapse:collapse;margin-bottom:16px;'>"
        f"<tr><td style='padding:6px 12px;font-weight:bold;'>שם:</td><td style='padding:6px 12px;'>{client_name}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:bold;'>טלפון:</td><td style='padding:6px 12px;direction:ltr;'>{client_phone}</td></tr>"
        "</table>"
        "<h4>תמליל שיחה:</h4>"
        f"<div style='background:#f8f9fa;padding:12px;border-radius:8px;font-size:13px;white-space:pre-wrap;direction:rtl;'>{transcript}</div>"
        "</body></html>"
    )
    payload = json.dumps({
        "Messages": [{
            "From": {"Email": FROM_EMAIL, "Name": FROM_NAME},
            "To": [{"Email": agent_email}],
            "Subject": subject,
            "HTMLPart": html,
        }]
    }).encode()
    credentials = base64.b64encode(f"{MAILJET_API_KEY}:{MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=payload,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[AGENT ALERT] sent to {agent_email}")
    except Exception as e:
        print(f"[AGENT ALERT ERROR] {e}")


def send_hot_lead_alert(name: str, phone: str, score: str, transcript: str) -> None:
    """שולח התראת לקוח חם ל-projects@orencohengroup.com"""
    score_emoji = {"High": "🔴 HIGH", "Medium": "🟠 MEDIUM", "Low": "🟢 LOW"}.get(score, score)
    subject = f"🔥 לקוח חם מהבוט — {name} ({phone})"
    html = (
        "<html><body dir='rtl' style='font-family:Arial,sans-serif;font-size:14px;'>"
        "<h2 style='color:#dc2626;'>🔥 לקוח חם מהבוט!</h2>"
        "<table style='border-collapse:collapse;margin-bottom:16px;'>"
        f"<tr><td style='padding:6px 12px;font-weight:bold;'>שם:</td><td style='padding:6px 12px;'>{name}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:bold;'>טלפון:</td><td style='padding:6px 12px;'>{phone}</td></tr>"
        f"<tr><td style='padding:6px 12px;font-weight:bold;'>ציון:</td><td style='padding:6px 12px;'>{score_emoji}</td></tr>"
        "</table><h4>תמליל שיחה:</h4>"
        f"<div style='background:#f8f9fa;padding:12px;border-radius:8px;font-size:13px;white-space:pre-wrap;direction:rtl;'>{transcript}</div>"
        "</body></html>"
    )
    payload = json.dumps({
        "Messages": [{
            "From": {"Email": FROM_EMAIL, "Name": FROM_NAME},
            "To": [{"Email": "projects@orencohengroup.com"}],
            "Subject": subject,
            "HTMLPart": html,
        }]
    }).encode()
    credentials = base64.b64encode(f"{MAILJET_API_KEY}:{MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=payload,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[HOT LEAD ALERT] sent for {phone}")
    except Exception as e:
        print(f"[HOT LEAD ALERT ERROR] {e}")


def send_shishi_registration(name: str, phone: str, guests: str) -> None:
    """שולח מייל על הרשמה חדשה לשישי של פעם דרך Gmail SMTP."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    gmail_user = os.getenv("GMAIL_USER", "orencohengroup2020@gmail.com")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")

    subject = f"🎉 הרשמה חדשה — שישי של פעם | {name}"
    html = (
        "<html><body dir='rtl' style='font-family:Arial,sans-serif;font-size:14px;'>"
        "<h2 style='color:#c9a84c;'>הרשמה חדשה — שישי של פעם</h2>"
        "<table style='border-collapse:collapse;'>"
        f"<tr><td style='padding:6px 16px;font-weight:bold;'>שם:</td><td style='padding:6px 16px;'>{name}</td></tr>"
        f"<tr><td style='padding:6px 16px;font-weight:bold;'>טלפון:</td><td style='padding:6px 16px;direction:ltr;'>{phone}</td></tr>"
        f"<tr><td style='padding:6px 16px;font-weight:bold;'>מספר משתתפים:</td><td style='padding:6px 16px;'>{guests}</td></tr>"
        "</table></body></html>"
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("בוט אורן כהן גרופ", gmail_user))
    msg["To"] = "office@orencohengroup.com"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, "office@orencohengroup.com", msg.as_string())
        print(f"[SHISHI] email sent for {name} {phone}")
    except Exception as e:
        print(f"[SHISHI EMAIL ERROR] {e}")


def send_shishi_daily_report(registrations: list) -> None:
    """שולח סיכום יומי של הרשמות שישי של פעם ב-16:00."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    gmail_user = os.getenv("GMAIL_USER", "orencohengroup2020@gmail.com")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")

    total_people = sum(int(r.get("guests", 1)) for r in registrations)
    rows = "".join(
        f"<tr><td style='padding:8px;border:1px solid #ddd;'>{r.get('name','')}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;direction:ltr;'>{r.get('phone','')}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;text-align:center;'>{r.get('guests',1)}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;font-size:11px;color:#888;'>{r.get('created_at','')[:16]}</td></tr>"
        for r in registrations
    )
    html = f"""
    <html><body dir="rtl" style="font-family:Arial,sans-serif;font-size:14px;">
      <h2 style="color:#c9a84c;">סיכום הרשמות — שישי של פעם</h2>
      <p>סה"כ נרשמו: <strong>{len(registrations)} אנשים</strong> | סה"כ משתתפים: <strong>{total_people}</strong></p>
      <table style="border-collapse:collapse;width:100%;margin-top:12px;">
        <thead><tr style="background:#f0f0f0;">
          <th style="padding:8px;border:1px solid #ddd;">שם</th>
          <th style="padding:8px;border:1px solid #ddd;">טלפון</th>
          <th style="padding:8px;border:1px solid #ddd;">משתתפים</th>
          <th style="padding:8px;border:1px solid #ddd;">זמן הרשמה</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </body></html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📋 סיכום הרשמות שישי של פעם — {len(registrations)} נרשמו ({total_people} משתתפים)"
    msg["From"] = formataddr(("בוט אורן כהן גרופ", gmail_user))
    msg["To"] = "office@orencohengroup.com"
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, "office@orencohengroup.com", msg.as_string())
        print(f"[SHISHI REPORT] sent {len(registrations)} regs")
    except Exception as e:
        print(f"[SHISHI REPORT ERROR] {e}")


def send_bulk_report(agent_label: str, results: list[dict], agent_email: str | None = None) -> None:
    """שולח דוח שליחה מיידי לאדמין עם סיכום מה עבד ומה לא."""
    sent = [r for r in results if r["status"] == "sent"]
    failed = [r for r in results if r["status"] == "error"]

    rows = ""
    for r in results:
        ok = r["status"] == "sent"
        icon = "✅" if ok else "❌"
        reason = r.get("reason", "") if not ok else ""
        rows += f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;">{r.get('phone','')}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">{icon}</td>
          <td style="padding:8px;border:1px solid #ddd;color:#c00;font-size:12px;">{reason}</td>
        </tr>"""

    html = f"""
    <html><body dir="rtl" style="font-family:Arial,sans-serif;font-size:14px;">
      <h2>דוח שליחת WhatsApp — {agent_label}</h2>
      <p>✅ נשלח: <strong>{len(sent)}</strong> &nbsp;|&nbsp; ❌ נכשל: <strong>{len(failed)}</strong></p>
      <table style="border-collapse:collapse;width:100%;">
        <thead>
          <tr style="background:#f0f0f0;">
            <th style="padding:8px;border:1px solid #ddd;">טלפון</th>
            <th style="padding:8px;border:1px solid #ddd;">סטטוס</th>
            <th style="padding:8px;border:1px solid #ddd;">סיבה</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </body></html>
    """

    to_list = [{"Email": ADMIN_EMAIL}]
    if ADMIN_EMAIL2 and ADMIN_EMAIL2 != ADMIN_EMAIL:
        to_list.append({"Email": ADMIN_EMAIL2})
    if agent_email and agent_email != ADMIN_EMAIL and agent_email != ADMIN_EMAIL2:
        to_list.append({"Email": agent_email})

    # שלח ל-ADMIN רק אם יש שגיאות
    if not failed:
        to_list = [t for t in to_list if t["Email"] != ADMIN_EMAIL]
    if not to_list:
        return

    payload = json.dumps({
        "Messages": [{
            "From": {"Email": FROM_EMAIL, "Name": FROM_NAME},
            "To": to_list,
            "Subject": f"דוח שליחת WhatsApp — {agent_label} ({len(sent)}✅ {len(failed)}❌)",
            "HTMLPart": html,
        }]
    }).encode()

    credentials = base64.b64encode(f"{MAILJET_API_KEY}:{MAILJET_SECRET_KEY}".encode()).decode()
    req = urllib.request.Request(
        "https://api.mailjet.com/v3.1/send",
        data=payload,
        headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(f"[ADMIN REPORT] sent to {[t['Email'] for t in to_list]} | response={body[:200]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ADMIN REPORT ERROR] HTTP {e.code}: {body}")
    except Exception as e:
        print(f"[ADMIN REPORT ERROR] {e}")
