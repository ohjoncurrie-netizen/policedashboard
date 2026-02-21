"""
Morning Briefing - emails a daily digest of yesterday's posts.
Sends to the admin and to all active public subscribers.
Runs daily at 7am via cron.
"""

import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

import config

ADMIN_EMAIL = "ohjoncurrie@gmail.com"


def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_posts_for_date(date_str, counties=None):
    """Return posts for a given YYYY-MM-DD date, optionally filtered by county list."""
    conn = get_db()
    sql = """
        SELECT p.title, p.summary, p.agency_name, p.county, p.incident_date
        FROM posts p
        WHERE (p.incident_date = ? OR DATE(p.created_at) = ?)
    """
    params = [date_str, date_str]
    if counties:
        placeholders = ','.join('?' * len(counties))
        sql += f" AND p.county IN ({placeholders})"
        params.extend(counties)
    sql += " ORDER BY p.incident_date, p.created_at"
    posts = conn.execute(sql, params).fetchall()
    conn.close()
    return posts


def build_html(posts, date_str, unsubscribe_url=None):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
    <h2 style="color:#1e293b;">Montana Blotter: Morning Briefing</h2>
    <p style="color:#64748b;"><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
    <p style="color:#64748b;">{len(posts)} report(s) from {date_str}</p>
    <hr style="border:1px solid #e2e8f0;">
    """
    for post in posts:
        agency = post['agency_name'] or post['county'] or 'Unknown Agency'
        summary_html = (post['summary'] or '').replace('\n', '<br>')
        html += f"""
        <h3 style="color:#1e293b;">{post['title'] or 'Daily Activity Report'}</h3>
        <p style="color:#64748b;font-size:13px;">{agency} &mdash; {post['incident_date'] or date_str}</p>
        <p style="color:#374151;line-height:1.6;">{summary_html}</p>
        <hr style="border:1px solid #e2e8f0;">
        """
    html += f"""
    <p style="color:#94a3b8;font-size:12px;margin-top:24px;">
        <a href="https://montanablotters.com" style="color:#3b82f6;">montanablotters.com</a>
    """
    if unsubscribe_url:
        html += f' &mdash; <a href="{unsubscribe_url}" style="color:#94a3b8;">Unsubscribe</a>'
    html += "</p></div>"
    return html


def send_email(to_addr, subject, html_body):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = config.EMAIL_USER
    msg['To'] = to_addr
    msg.attach(MIMEText(html_body, 'html'))
    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.EMAIL_USER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_USER, to_addr, msg.as_string())


def run_briefing():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    subject = f"Montana Blotter Briefing – {datetime.now().strftime('%b %d, %Y')}"

    # --- Admin briefing (all counties) ---
    posts = get_posts_for_date(yesterday)
    if posts:
        html = build_html(posts, yesterday)
        try:
            send_email(ADMIN_EMAIL, subject, html)
            print(f"Admin briefing sent ({len(posts)} posts)")
        except Exception as e:
            print(f"Admin briefing failed: {e}")
    else:
        print(f"No posts for {yesterday} — skipping admin briefing.")

    # --- Public subscriber briefings ---
    conn = get_db()
    subscribers = conn.execute(
        'SELECT email, counties, token FROM subscribers WHERE active=1'
    ).fetchall()
    conn.close()

    sent = skipped = 0
    for sub in subscribers:
        county_filter = [c.strip() for c in (sub['counties'] or '').split(',') if c.strip()]
        sub_posts = get_posts_for_date(yesterday, county_filter or None)
        if not sub_posts:
            skipped += 1
            continue
        unsub_url = f"https://montanablotters.com/unsubscribe?token={sub['token']}"
        html = build_html(sub_posts, yesterday, unsubscribe_url=unsub_url)
        try:
            send_email(sub['email'], subject, html)
            sent += 1
        except Exception as e:
            print(f"Failed to send to {sub['email']}: {e}")

    print(f"Subscriber briefings: {sent} sent, {skipped} skipped (no matching posts)")


if __name__ == "__main__":
    run_briefing()
