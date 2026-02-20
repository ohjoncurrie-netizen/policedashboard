import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# --- CONFIGURATION ---
DB_PATH = "/root/montanablotter/records_metadata.db"
EMAIL_USER = "juan@fertherecerd.com"
EMAIL_PASS = "Lol123lol!!"  # The same 16-character code used before
RECIPIENT_EMAIL = "ohjoncurrie@gmail.com"

def get_daily_summaries():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # We fetch records from the last 24 hours
    # Note: This assumes you added a 'timestamp' column or we just pull the latest 10
    query = "SELECT filename, summary FROM summaries ORDER BY id DESC LIMIT 10"
    records = conn.execute(query).fetchall()
    conn.close()
    return records

def send_briefing(records):
    if not records:
        print("No new records to report today.")
        return

    # Build HTML Email Body
    html = f"<h2>🏔️ Montana Blotter: Morning Briefing</h2>"
    html += f"<p>Date: {datetime.now().strftime('%Y-%m-%d')}</p><hr>"
    
    for rec in records:
        html += f"<h3>📄 {rec['filename']}</h3>"
        html += f"<p>{rec['summary'].replace('\n', '<br>')}</p><br>"

    msg = MIMEMultipart()
    msg['Subject'] = f"Montana Blotter Briefing - {datetime.now().strftime('%b %d')}"
    msg['From'] = EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html, 'html'))

    # Send via Gmail SMTP
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        print("Briefing sent successfully!")
    except Exception as e:
        print(f"Error sending briefing: {e}")

if __name__ == "__main__":
    latest_records = get_daily_summaries()
    send_briefing(latest_records)


