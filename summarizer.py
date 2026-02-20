"""
Summarizer - Uses Claude to generate a single daily digest post per blotter.

REQUIREMENT: config.py must contain:
    ANTHROPIC_API_KEY = 'sk-ant-...'
"""

import json
import logging
import re
import sqlite3

import config

DB_PATH = config.DB_PATH
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agency detection
# ---------------------------------------------------------------------------

def _detect_agency(content: str, sender_email: str = None,
                   filename: str = None, county: str = None) -> tuple[str, str]:
    """
    Return (agency_type, agency_name) by checking filename first, then
    content keywords, then sender_email.
    agency_type: 'sheriff' | 'police' | 'other'
    """
    # Known agency abbreviations in filenames
    fname = (filename or "").upper()
    if "GCSO" in fname:
        return "sheriff", f"{county or 'Gallatin'} County Sheriff's Office"
    if "LCSO" in fname:
        return "sheriff", f"{county or 'Lewis and Clark'} County Sheriff's Office"
    if re.search(r'\bSO\b', fname):          # e.g. "MTSO", "YCSO"
        return "sheriff", f"{county or ''} County Sheriff's Office".strip()
    if re.search(r'\bPD\b', fname):
        return "police", f"{county or ''} Police Department".strip()

    content_upper = content.upper() if content else ""

    if "SHERIFF" in content_upper:
        m = re.search(r"([A-Za-z\s]+(?:County)?\s+Sheriff(?:'?s)?\s+Office)", content, re.IGNORECASE)
        return "sheriff", (m.group(1).strip() if m else f"{county or ''} Sheriff's Office".strip())

    if "POLICE DEPARTMENT" in content_upper or re.search(r'\bPD\b', content or ""):
        m = re.search(r"([A-Za-z\s]+Police\s+Department)", content, re.IGNORECASE)
        return "police", (m.group(1).strip() if m else f"{county or ''} Police Department".strip())

    if sender_email:
        local = sender_email.split("@")[0].lower()
        if "sheriff" in local:
            return "sheriff", f"{county or ''} Sheriff's Office".strip()
        if local in ("pd", "police"):
            return "police", f"{county or ''} Police Department".strip()

    return "other", ""


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------

def generate_posts(blotter_id: int, sender_email: str = None) -> int:
    """
    Generate one daily digest post for the blotter if one doesn't exist yet.
    Returns 1 if created, 0 if already exists or no records found.

    Requires config.ANTHROPIC_API_KEY.
    Falls back to a plain-text digest on any Claude API failure.
    """
    try:
        import anthropic
        api_key = getattr(config, "ANTHROPIC_API_KEY", None)
        client = anthropic.Anthropic(api_key=api_key) if api_key else None
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set – using fallback digest")
    except ImportError:
        logger.warning("anthropic not installed – using fallback digest")
        client = None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Skip if a post already exists for this blotter
    existing = cursor.execute(
        "SELECT id FROM posts WHERE blotter_id = ?", (blotter_id,)
    ).fetchone()
    if existing:
        conn.close()
        logger.info(f"Post already exists for blotter {blotter_id} – skipping")
        return 0

    # Fetch blotter metadata
    blotter_row = cursor.execute(
        "SELECT county, upload_date, filename FROM blotters WHERE id = ?", (blotter_id,)
    ).fetchone()
    blotter_county = blotter_row["county"] if blotter_row else "Unknown"
    blotter_date = (blotter_row["upload_date"] or "")[:10] if blotter_row else ""
    blotter_filename = blotter_row["filename"] if blotter_row else ""

    # Fetch all records for this blotter, sorted chronologically
    rows = cursor.execute(
        """
        SELECT
            COALESCE(r.incident_type, r.incident, '') AS incident_type,
            r.location,
            r.date,
            COALESCE(r.time, '') AS time,
            r.county,
            COALESCE(r.officer, '') AS officer,
            COALESCE(r.details, r.summary, '') AS details
        FROM records r
        WHERE r.blotter_id = ?
        ORDER BY r.date, r.time
        """,
        (blotter_id,),
    ).fetchall()

    if not rows:
        conn.close()
        logger.info(f"No records for blotter {blotter_id} – nothing to post")
        return 0

    # Determine county and date from first record
    county = rows[0]["county"] or blotter_county
    incident_date = rows[0]["date"] or blotter_date

    # Build combined text for agency detection
    combined_text = " ".join(
        f"{r['incident_type']} {r['location']} {r['details']}" for r in rows
    )
    agency_type, agency_name = _detect_agency(
        combined_text, sender_email, filename=blotter_filename, county=county
    )

    # Format incident list for Claude
    incident_lines = []
    for r in rows:
        time_str = r["time"] or ""
        itype = r["incident_type"] or "Unknown"
        loc = r["location"] or ""
        detail = r["details"] or ""
        incident_lines.append(f"- {time_str}  {itype}  |  {loc}  |  {detail}".strip(" |"))

    post_data = _call_claude(
        client=client,
        county=county,
        date=incident_date,
        agency_type=agency_type,
        agency_name=agency_name,
        filename=blotter_filename,
        incident_lines=incident_lines,
    )

    final_agency_type = post_data.get("agency_type") or agency_type
    final_agency_name = post_data.get("agency_name") or agency_name
    city = post_data.get("city") or ""

    cursor.execute(
        """
        INSERT INTO posts
            (blotter_id, title, summary, city, county,
             agency_type, agency_name, incident_date, incident_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            blotter_id,
            post_data.get("title") or f"Daily Activity Report – {final_agency_name or county}",
            post_data.get("summary") or _fallback_summary(agency_name, rows),
            city,
            county,
            final_agency_type,
            final_agency_name,
            incident_date,
            "Daily Digest",
        ),
    )

    conn.commit()
    conn.close()
    logger.info(f"generate_posts(blotter_id={blotter_id}): created 1 digest post")
    return 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_claude(client, county, date, agency_type, agency_name, filename, incident_lines) -> dict:
    """
    Call Claude to produce a single daily digest post.
    Returns dict with keys: title, summary, city, agency_type, agency_name.
    """
    if client is None:
        return {}

    agency_label = agency_name or f"{county} County {'Sheriff' if agency_type == 'sheriff' else 'Police'}"
    incidents_block = "\n".join(incident_lines)

    user_content = f"""Write a daily police activity report for publication.

Agency: {agency_label}
Agency type: {agency_type}
Source file: {filename}
Date: {date}
County: {county}

Incidents (time | type | location | details):
{incidents_block}

Format the summary exactly like this example — a short intro sentence, then one bullet per notable incident with the time and a plain-English description:

"The [Agency Name] responded to a variety of incidents throughout the day. Below is a summary of notable events:

[HH:MM AM/PM] – [Plain English description of incident and location.]
[HH:MM AM/PM] – [Plain English description of incident and location.]
..."

Skip purely administrative entries (voicemails, callbacks, no-answer checks).
Use natural times like "8:20 AM" not raw timestamps.
Keep each bullet to one sentence.

Return ONLY valid JSON with these keys:
{{
  "title": "Daily Police Activity Report – [Agency Name]",
  "summary": "[the full formatted report as described above]",
  "city": "primary city or town if determinable, else empty string",
  "agency_type": "sheriff or police or other",
  "agency_name": "full agency name"
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "You are a journalist writing daily police activity summaries for a public news site. "
                "Write clearly and factually. Respond with valid JSON only."
            ),
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Claude API error: {e} – using fallback digest")
        return {}


def _fallback_summary(agency_name: str, rows) -> str:
    """Plain-text digest when Claude is unavailable."""
    lines = [f"The {agency_name or 'agency'} responded to the following incidents:"]
    for r in rows:
        time_str = r["time"] or ""
        itype = r["incident_type"] or "Incident"
        loc = r["location"] or ""
        lines.append(f"{time_str} – {itype}" + (f" at {loc}" if loc else ""))
    return "\n".join(lines)
