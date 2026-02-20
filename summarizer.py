"""
Summarizer - Uses Claude to generate readable posts from blotter records.

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

def _detect_agency(content: str, sender_email: str = None) -> tuple[str, str]:
    """
    Return (agency_type, agency_name) by inspecting content then sender_email.

    agency_type: 'sheriff' | 'police' | 'other'
    agency_name: best human-readable name found, or empty string
    """
    content_upper = content.upper() if content else ""

    # Content-first detection
    if "SHERIFF" in content_upper:
        # Try to extract a proper name like "Gallatin County Sheriff's Office"
        m = re.search(r"([A-Za-z\s]+(?:County)?\s+Sheriff(?:'?s)?\s+Office)", content, re.IGNORECASE)
        agency_name = m.group(1).strip() if m else "Sheriff's Office"
        return "sheriff", agency_name

    if "POLICE DEPARTMENT" in content_upper or re.search(r'\bPD\b', content):
        m = re.search(r"([A-Za-z\s]+Police\s+Department)", content, re.IGNORECASE)
        agency_name = m.group(1).strip() if m else "Police Department"
        return "police", agency_name

    # Fall back to sender email
    if sender_email:
        local = sender_email.split("@")[0].lower()
        if "sheriff" in local:
            return "sheriff", "Sheriff's Office"
        if local in ("pd", "police"):
            return "police", "Police Department"

    return "other", ""


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------

def generate_posts(blotter_id: int, sender_email: str = None) -> int:
    """
    Generate AI-summarized posts for all records in blotter_id that don't
    already have a post.  Returns number of posts created.

    Requires config.ANTHROPIC_API_KEY to be set.
    Falls back to a simple post on any Claude API failure so the pipeline
    never blocks.
    """
    try:
        import anthropic
        api_key = getattr(config, "ANTHROPIC_API_KEY", None)
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set in config.py – using fallback posts")
            client = None
        else:
            client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("anthropic package not installed – using fallback posts")
        client = None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Records for this blotter that don't yet have a post.
    # COALESCE handles old schema ('incident') and new schema ('incident_type').
    rows = cursor.execute(
        """
        SELECT
            r.id,
            r.blotter_id,
            COALESCE(r.incident_type, r.incident, '') AS incident_type,
            r.location,
            r.date,
            COALESCE(r.time, '')   AS time,
            r.county,
            COALESCE(r.officer, '') AS officer,
            COALESCE(r.details, r.summary, '') AS details
        FROM records r
        LEFT JOIN posts p ON p.record_id = r.id
        WHERE r.blotter_id = ?
          AND p.id IS NULL
        """,
        (blotter_id,),
    ).fetchall()

    # Also fetch county from blotter for agency detection fallback
    blotter_row = cursor.execute(
        "SELECT county FROM blotters WHERE id = ?", (blotter_id,)
    ).fetchone()
    blotter_county = blotter_row["county"] if blotter_row else "Unknown"

    created = 0
    for row in rows:
        record_id = row["id"]
        incident_type = row["incident_type"] or "Unknown Incident"
        location = row["location"] or ""
        date = row["date"] or ""
        time = row["time"] or ""
        county = row["county"] or blotter_county
        officer = row["officer"] or ""
        details = row["details"] or ""

        # Fetch command log entries
        logs = cursor.execute(
            "SELECT timestamp, officer, entry FROM command_logs WHERE record_id = ? ORDER BY timestamp",
            (record_id,),
        ).fetchall()
        log_lines = "\n".join(
            f"  [{lg['timestamp']}] {lg['officer']}: {lg['entry']}" for lg in logs
        )

        combined_text = f"{incident_type} {location} {details} {log_lines}"
        agency_type, agency_name = _detect_agency(combined_text, sender_email)

        post_data = _call_claude(
            client=client,
            incident_type=incident_type,
            location=location,
            date=date,
            time=time,
            county=county,
            officer=officer,
            details=details,
            log_lines=log_lines,
            fallback_agency_type=agency_type,
            fallback_agency_name=agency_name,
        )

        # Infer city from location (first meaningful token)
        city = post_data.get("city") or _city_from_location(location)

        # Override agency fields if Claude provided them
        final_agency_type = post_data.get("agency_type") or agency_type
        final_agency_name = post_data.get("agency_name") or agency_name

        cursor.execute(
            """
            INSERT INTO posts
                (record_id, blotter_id, title, summary, city, county,
                 agency_type, agency_name, incident_date, incident_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                blotter_id,
                post_data.get("title") or incident_type,
                post_data.get("summary") or details,
                city,
                county,
                final_agency_type,
                final_agency_name,
                date,
                incident_type,
            ),
        )
        created += 1

    conn.commit()
    conn.close()
    logger.info(f"generate_posts(blotter_id={blotter_id}): created {created} posts")
    return created


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_claude(
    client,
    incident_type,
    location,
    date,
    time,
    county,
    officer,
    details,
    log_lines,
    fallback_agency_type,
    fallback_agency_name,
) -> dict:
    """
    Call Claude to summarize one incident.  Returns a dict with keys:
    title, summary, city, agency_type, agency_name.
    Falls back gracefully on any error.
    """
    if client is None:
        return _fallback_post(incident_type, details, fallback_agency_type, fallback_agency_name)

    user_content = f"""Incident details to summarize:

Type: {incident_type}
Location: {location}
Date/Time: {date} {time}
County: {county}
Officer: {officer}
Details: {details}

Command log:
{log_lines if log_lines else '(none)'}

Return ONLY a JSON object with these exact keys:
{{
  "title": "short headline (10 words max)",
  "summary": "2-3 sentence plain-English summary for a news reader",
  "city": "city or town name extracted from location, or empty string",
  "agency_type": "sheriff or police or other",
  "agency_name": "full agency name, e.g. Gallatin County Sheriff's Office"
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=(
                "You are a journalist assistant that summarizes police blotter incidents "
                "into short, factual, readable posts for a public news site. "
                "Respond with valid JSON only."
            ),
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return data
    except Exception as e:
        logger.warning(f"Claude API error: {e} – using fallback post")
        return _fallback_post(incident_type, details, fallback_agency_type, fallback_agency_name)


def _fallback_post(incident_type, details, agency_type, agency_name) -> dict:
    return {
        "title": incident_type,
        "summary": details or incident_type,
        "city": "",
        "agency_type": agency_type or "other",
        "agency_name": agency_name or "",
    }


def _city_from_location(location: str) -> str:
    """Best-effort city extraction from a location string."""
    if not location:
        return ""
    # Strip unit/apt suffixes, take first meaningful segment
    parts = re.split(r"[,;/]", location)
    candidate = parts[0].strip()
    # Remove leading numbers (street addresses)
    candidate = re.sub(r"^\d+\s+", "", candidate)
    return candidate[:80]
