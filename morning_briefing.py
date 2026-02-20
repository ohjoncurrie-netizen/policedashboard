"""
Morning Briefing - emails a daily digest of yesterday's posts to the admin.
Runs daily at 7am via cron.
"""

import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

import config

RECIPIENT_EMAIL = "ohjoncurrie@gmail.com"


def get_yesterdays_posts():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    posts = conn.execute(
        """
        SELECT p.title, p.summary, p.agency_name, p.county, p.incident_date
        FROM posts p
        WHERE p.incident_date = ? OR DATE(p.created_at) = ?
        ORDER BY p.incident_date, p.created_at
        """,
        (yesterday, yesterday),
    ).fetchall()
    conn.close()
    return posts, yesterday


def send_briefing(posts, date_str):
    if not posts:
        print(f"No new posts for {date_str} — skipping briefing email.")
        return

    html = f"""
    <h2>Montana Blotter: Morning Briefing</h2>
    <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
    <p>{len(posts)} report(s) from {date_str}</p>
    <hr>
    """

    for post in posts:
        agency = post['agency_name'] or post['county'] or 'Unknown Agency'
        summary_html = (post['summary'] or '').replace('\n', '<br>')
        html += f"""
        <h3>{post['title'] or 'Daily Activity Report'}</h3>
        <p style="color:#666;font-size:13px;">{agency} &mdash; {post['incident_date'] or date_str}</p>
        <p>{summary_html}</p>
        <hr>
        """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Montana Blotter Briefing – {datetime.now().strftime('%b %d, %Y')}"
    msg['From'] = config.EMAIL_USER
    msg['To'] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_USER, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        print(f"Briefing sent to {RECIPIENT_EMAIL} ({len(posts)} posts)")
    except Exception as e:
        print(f"Error sending briefing: {e}")


if __name__ == "__main__":
    posts, date_str = get_yesterdays_posts()
    send_briefing(posts, date_str)
