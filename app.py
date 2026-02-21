"""
Montana Blotter - Simplified Free & Open Source Version
Public browse + Admin panel only (no memberships)
"""

import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from datetime import datetime
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Apply DB migrations at startup
from init_db import migrate as _migrate
_migrate()
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'

# File upload configuration
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = config.UPLOAD_DIR

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    res = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if res:
        return User(res['id'], res['username'])
    return None

# ==========================================
# PUBLIC ROUTES (No Login Required)
# ==========================================

@app.route('/')
def index():
    """Public homepage — daily activity reports with calendar filter"""
    county      = request.args.get('county', '')
    city        = request.args.get('city', '')
    agency_type = request.args.get('agency_type', '')
    agency      = request.args.get('agency', '')   # specific agency_name
    search_query = request.args.get('q', '')
    date_filter = request.args.get('date', '')   # expects YYYY-MM-DD
    page        = max(1, request.args.get('page', 1, type=int))
    per_page    = 10

    conn = get_db()

    # Convert YYYY-MM-DD date_filter → MM/DD/YY for DB match
    date_sql_val = ''
    if date_filter:
        try:
            dt = datetime.strptime(date_filter, '%Y-%m-%d')
            date_sql_val = dt.strftime('%m/%d/%y')
        except ValueError:
            date_filter = ''

    sql = """
        SELECT posts.*, blotters.county AS blotter_county
        FROM posts
        JOIN blotters ON posts.blotter_id = blotters.id
        WHERE 1=1
    """
    params = []

    if county:
        sql += " AND posts.county = ?"
        params.append(county)
    if city:
        sql += " AND posts.city LIKE ?"
        params.append(f'%{city}%')
    if agency_type:
        sql += " AND posts.agency_type = ?"
        params.append(agency_type)
    if agency:
        sql += " AND posts.agency_name = ?"
        params.append(agency)
    if search_query:
        st = f'%{search_query}%'
        sql += " AND (posts.title LIKE ? OR posts.summary LIKE ?)"
        params.extend([st, st])
    if date_sql_val:
        sql += " AND posts.incident_date = ?"
        params.append(date_sql_val)

    count_sql = sql.replace(
        "SELECT posts.*, blotters.county AS blotter_county", "SELECT COUNT(*)")
    total = conn.execute(count_sql, params).fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)

    sql += " ORDER BY posts.incident_date DESC, posts.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    posts = conn.execute(sql, params).fetchall()

    # Filter dropdowns
    counties = [r['county'] for r in conn.execute(
        'SELECT DISTINCT county FROM posts ORDER BY county').fetchall()]
    cities = [r['city'] for r in conn.execute(
        "SELECT DISTINCT city FROM posts WHERE city != '' ORDER BY city").fetchall()]

    # Agency directory: each agency with last report date and count
    agencies = conn.execute("""
        SELECT agency_name, agency_type,
               MAX(incident_date) AS last_report,
               COUNT(*) AS report_count
        FROM posts
        WHERE agency_name IS NOT NULL AND agency_name != ''
        GROUP BY agency_name
        ORDER BY last_report DESC
    """).fetchall()

    # Calendar: all dates that have at least one post, normalised to YYYY-MM-DD
    dates_with_posts = []
    for row in conn.execute(
            'SELECT DISTINCT incident_date FROM posts '
            'WHERE incident_date IS NOT NULL AND incident_date != "" '
            'ORDER BY incident_date').fetchall():
        try:
            d = datetime.strptime(row[0], '%m/%d/%y').strftime('%Y-%m-%d')
            dates_with_posts.append(d)
        except ValueError:
            pass

    total_records = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]

    # Leaderboard: most active agencies this week vs last week
    this_week_rows = conn.execute("""
        SELECT COALESCE(county, 'Unknown') AS county,
               COUNT(*) AS cnt
        FROM records
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY county ORDER BY cnt DESC LIMIT 6
    """).fetchall()
    prev_week_map = {r['county']: r['cnt'] for r in conn.execute("""
        SELECT COALESCE(county, 'Unknown') AS county, COUNT(*) AS cnt
        FROM records
        WHERE created_at >= datetime('now', '-14 days')
          AND created_at < datetime('now', '-7 days')
        GROUP BY county
    """).fetchall()}
    leaderboard = []
    for r in this_week_rows:
        prev = prev_week_map.get(r['county'], 0)
        trend = 'up' if r['cnt'] > prev else ('down' if r['cnt'] < prev else 'same')
        leaderboard.append({'county': r['county'], 'count': r['cnt'],
                            'prev': prev, 'trend': trend})

    conn.close()

    return render_template('index.html',
                           posts=posts,
                           total=total,
                           total_pages=total_pages,
                           page=page,
                           counties=counties,
                           cities=cities,
                           agencies=agencies,
                           county=county,
                           city=city,
                           agency_type=agency_type,
                           agency=agency,
                           q=search_query,
                           date_filter=date_filter,
                           dates_with_posts=dates_with_posts,
                           total_records=total_records,
                           leaderboard=leaderboard)


@app.route('/feed.xml')
def rss_feed():
    """Atom feed of the 20 most recent daily activity reports."""
    conn = get_db()
    posts = conn.execute("""
        SELECT posts.*, blotters.county AS blotter_county
        FROM posts
        JOIN blotters ON posts.blotter_id = blotters.id
        ORDER BY posts.incident_date DESC, posts.created_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    # Build RFC-3339 timestamps
    def to_rfc3339(date_str, created_at):
        for fmt in ('%m/%d/%y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%dT00:00:00Z')
            except (ValueError, TypeError):
                pass
        try:
            return datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%SZ')
        except (ValueError, TypeError):
            pass
        return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    items = []
    for p in posts:
        pub = to_rfc3339(p['incident_date'], p['created_at'])
        summary_snippet = (p['summary'] or '')[:300].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        title = (p['title'] or 'Daily Activity Report').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        agency = (p['agency_name'] or 'Montana Blotter').replace('&', '&amp;')
        link = f"https://montanablotters.com/?date={pub[:10]}&amp;agency={agency}"
        items.append(f"""  <entry>
    <title>{title}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{pub}</updated>
    <author><name>{agency}</name></author>
    <summary type="text">{summary_snippet}</summary>
  </entry>""")

    updated = to_rfc3339(posts[0]['incident_date'], posts[0]['created_at']) if posts else datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Montana Blotter — Daily Activity Reports</title>
  <subtitle>AI-summarized police blotters from Montana law enforcement agencies</subtitle>
  <link href="https://montanablotters.com/feed.xml" rel="self"/>
  <link href="https://montanablotters.com/"/>
  <id>https://montanablotters.com/feed.xml</id>
  <updated>{updated}</updated>
{chr(10).join(items)}
</feed>"""

    from flask import Response
    return Response(xml, mimetype='application/atom+xml')


@app.route('/arrests')
def arrests():
    """Dedicated arrest log — records where an arrest was made."""
    county = request.args.get('county', '')
    search_query = request.args.get('q', '')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 25

    conn = get_db()

    arrest_filter = """(
        LOWER(COALESCE(records.details, '')) LIKE '%arrest%'
        OR LOWER(COALESCE(records.incident_type, '')) LIKE '%arrest%'
        OR LOWER(COALESCE(records.incident, '')) LIKE '%arrest%'
    )"""

    sql = f"""
        SELECT records.*,
               COALESCE(blotters.filename, '') AS filename
        FROM records
        LEFT JOIN blotters ON records.blotter_id = blotters.id
        WHERE {arrest_filter}
    """
    params = []

    if county:
        sql += " AND records.county = ?"
        params.append(county)
    if search_query:
        st = f'%{search_query}%'
        sql += " AND (records.incident_type LIKE ? OR records.details LIKE ? OR records.location LIKE ?)"
        params.extend([st, st, st])

    total = conn.execute(
        sql.replace("SELECT records.*,\n               COALESCE(blotters.filename, '') AS filename", "SELECT COUNT(*)"),
        params).fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)

    sql += " ORDER BY records.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    records = conn.execute(sql, params).fetchall()

    counties = [r['county'] for r in conn.execute(
        'SELECT DISTINCT county FROM records ORDER BY county').fetchall()]

    conn.close()
    return render_template('arrests.html',
                           records=records, total=total,
                           total_pages=total_pages, page=page,
                           counties=counties, county=county,
                           q=search_query)


@app.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    """Public email digest subscription."""
    import secrets

    conn = get_db()
    all_counties = [r['county'] for r in conn.execute(
        'SELECT DISTINCT county FROM posts ORDER BY county').fetchall()]

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        selected = request.form.getlist('counties')  # empty list = all counties

        if not email or '@' not in email:
            conn.close()
            return render_template('subscribe.html', counties=all_counties,
                                   error='Please enter a valid email address.')

        token = secrets.token_urlsafe(32)
        counties_str = ','.join(selected)

        try:
            conn.execute(
                'INSERT INTO subscribers (email, counties, token) VALUES (?, ?, ?)',
                (email, counties_str, token))
            conn.commit()
            conn.close()
            return render_template('subscribe.html', counties=all_counties,
                                   success=True, email=email)
        except Exception:
            # Email already subscribed — update preferences
            conn.execute(
                'UPDATE subscribers SET counties=?, active=1 WHERE email=?',
                (counties_str, email))
            conn.commit()
            conn.close()
            return render_template('subscribe.html', counties=all_counties,
                                   success=True, email=email, updated=True)

    conn.close()
    return render_template('subscribe.html', counties=all_counties)


@app.route('/unsubscribe')
def unsubscribe():
    """Unsubscribe via token link in digest emails."""
    token = request.args.get('token', '')
    conn = get_db()
    row = conn.execute('SELECT email FROM subscribers WHERE token=?', (token,)).fetchone()
    if row:
        conn.execute('UPDATE subscribers SET active=0 WHERE token=?', (token,))
        conn.commit()
        email = row['email']
        conn.close()
        return render_template('subscribe.html', counties=[], unsubscribed=True, email=email)
    conn.close()
    return render_template('subscribe.html', counties=[], error='Invalid or expired unsubscribe link.')


@app.route('/record/<int:record_id>')
def view_record(record_id):
    """Public view of individual record"""
    conn = get_db()
    
    record = conn.execute('''
        SELECT records.*, blotters.filename
        FROM records
        LEFT JOIN blotters ON records.blotter_id = blotters.id
        WHERE records.id = ?
    ''', (record_id,)).fetchone()
    
    if not record:
        flash('Record not found')
        conn.close()
        return redirect(url_for('index'))
    
    # Get command logs
    logs = conn.execute('''
        SELECT * FROM command_logs
        WHERE record_id = ?
        ORDER BY timestamp
    ''', (record_id,)).fetchall()
    
    conn.close()
    
    return render_template('record_detail.html', record=record, logs=logs)

@app.route('/posts')
def posts():
    """Public posts page with AI-summarized incidents"""
    county = request.args.get('county', '')
    city = request.args.get('city', '')
    agency_type = request.args.get('agency_type', '')
    q = request.args.get('q', '')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 20

    conn = get_db()

    # Build filter query
    sql = """
        SELECT posts.*, blotters.county as blotter_county
        FROM posts
        JOIN blotters ON posts.blotter_id = blotters.id
        WHERE 1=1
    """
    params = []

    if county:
        sql += " AND posts.county = ?"
        params.append(county)
    if city:
        sql += " AND posts.city LIKE ?"
        params.append(f'%{city}%')
    if agency_type:
        sql += " AND posts.agency_type = ?"
        params.append(agency_type)
    if q:
        sql += " AND (posts.title LIKE ? OR posts.summary LIKE ?)"
        term = f'%{q}%'
        params.extend([term, term])

    # Total count
    count_sql = f"SELECT COUNT(*) FROM ({sql})"
    total = conn.execute(count_sql, params).fetchone()[0]

    sql += " ORDER BY posts.incident_date DESC, posts.created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    post_rows = conn.execute(sql, params).fetchall()

    # Dropdown options
    counties = [r['county'] for r in conn.execute(
        'SELECT DISTINCT county FROM posts ORDER BY county').fetchall()]
    cities = [r['city'] for r in conn.execute(
        "SELECT DISTINCT city FROM posts WHERE city != '' ORDER BY city").fetchall()]

    conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        'posts.html',
        posts=post_rows,
        total=total,
        page=page,
        total_pages=total_pages,
        counties=counties,
        cities=cities,
        county=county,
        city=city,
        agency_type=agency_type,
        q=q,
    )


# ==========================================
# ADMIN ROUTES (Login Required)
# ==========================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        user_row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user_row and bcrypt.check_password_hash(user_row['password'], password):
            login_user(User(user_row['id'], user_row['username']))
            return redirect(url_for('admin_dashboard'))
        
        flash('Invalid credentials')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard with stats and management"""
    
    conn = get_db()
    
    # Get statistics
    total_records = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    total_blotters = conn.execute('SELECT COUNT(*) FROM blotters').fetchone()[0]
    total_counties = conn.execute('SELECT COUNT(DISTINCT county) FROM records').fetchone()[0]
    
    # Get recent blotters
    recent_blotters = conn.execute('''
        SELECT * FROM blotters 
        ORDER BY upload_date DESC 
        LIMIT 10
    ''').fetchall()
    
    # Get county breakdown
    county_stats = conn.execute('''
        SELECT county, COUNT(*) as count 
        FROM records 
        GROUP BY county 
        ORDER BY count DESC
    ''').fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html',
                         total_records=total_records,
                         total_blotters=total_blotters,
                         total_counties=total_counties,
                         recent_blotters=recent_blotters,
                         county_stats=county_stats)

@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def admin_upload():
    """Admin PDF upload"""
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        county = request.form.get('county', '')
        
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Process the PDF
            try:
                from processor import process_new_blotter
                batch_id = process_new_blotter(filepath, county if county else None)
                flash(f'✅ Successfully processed! Batch #{batch_id} with incidents added.')
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                flash(f'Error processing PDF: {str(e)}')
                return redirect(request.url)
        
        flash('Invalid file type. PDF only.')
        return redirect(request.url)
    
    # GET request - show upload form
    return render_template('admin_upload.html', counties=config.MONTANA_COUNTIES)

@app.route('/admin/blotters')
@login_required
def admin_blotters():
    """View and manage all blotters"""
    conn = get_db()
    blotters = conn.execute('SELECT * FROM blotters ORDER BY upload_date DESC').fetchall()
    conn.close()
    
    return render_template('admin_blotters.html', blotters=blotters)

@app.route('/admin/blotter/<int:blotter_id>/delete', methods=['POST'])
@login_required
def admin_delete_blotter(blotter_id):
    """Delete a blotter and its records"""
    conn = get_db()
    
    # Delete associated command logs first (via CASCADE this happens automatically)
    # Delete records (CASCADE will handle command_logs)
    conn.execute('DELETE FROM records WHERE blotter_id = ?', (blotter_id,))
    # Delete blotter
    conn.execute('DELETE FROM blotters WHERE id = ?', (blotter_id,))
    
    conn.commit()
    conn.close()
    
    flash('Blotter deleted successfully')
    return redirect(url_for('admin_blotters'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    """Admin settings - change password"""
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        
        if new_password:
            conn = get_db()
            hashed_pw = bcrypt.generate_password_hash(new_password).decode('utf-8')
            conn.execute('UPDATE users SET password = ? WHERE id = ?', 
                        (hashed_pw, current_user.id))
            conn.commit()
            conn.close()
            
            flash('Password updated successfully')
            return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_settings.html')

@app.route('/admin/emails', methods=['GET', 'POST'])
@login_required
def admin_emails():
    """Manage emails and send bulk emails to sheriffs"""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'send_to_sheriffs':
            # Get form data
            counties = request.form.getlist('counties')
            subject = request.form.get('subject', '')
            body = request.form.get('body', '')
            
            if not counties or not subject or not body:
                flash('Please select counties, provide subject and body')
                return redirect(url_for('admin_emails'))
            
            # Sheriffs email database (by county)
            SHERIFFS_EMAILS = {
                'Beaverhead': 'sheriff@beaverheadcounty.mt.gov',
                'Big Horn': 'sheriff@bighorncounty.mt.gov',
                'Blaine': 'sheriff@blainecounty.mt.gov',
                'Broadwater': 'sheriff@broadwatercounty.mt.gov',
                'Carbon': 'sheriff@carboncounty.mt.gov',
                'Carter': 'sheriff@cartercounty.mt.gov',
                'Cascade': 'sheriff@cascadecounty.mt.gov',
                'Chouteau': 'sheriff@choteaucounty.mt.gov',
                'Custer': 'sheriff@custercounty.mt.gov',
                'Daniels': 'sheriff@danielscounty.mt.gov',
                'Dawson': 'sheriff@dawsoncounty.mt.gov',
                'Deer Lodge': 'sheriff@deerlodgecounty.mt.gov',
                'Fallon': 'sheriff@falloncounty.mt.gov',
                'Fergus': 'sheriff@ferguscounty.mt.gov',
                'Flathead': 'sheriff@flatheadcounty.mt.gov',
                'Gallatin': 'sheriff@gallatincounty.mt.gov',
                'Garfield': 'sheriff@garfieldcounty.mt.gov',
                'Glacier': 'sheriff@glaciercounty.mt.gov',
                'Golden Valley': 'sheriff@goldenvalleycounty.mt.gov',
                'Granite': 'sheriff@granitecounty.mt.gov',
                'Hill': 'sheriff@hillcounty.mt.gov',
                'Jefferson': 'sheriff@jeffersoncounty.mt.gov',
                'Judith Basin': 'sheriff@judithbasincounty.mt.gov',
                'Lake': 'sheriff@lakecounty.mt.gov',
                'Lewis and Clark': 'sheriff@lewisandclarkcounty.mt.gov',
                'Liberty': 'sheriff@libertycounty.mt.gov',
                'Lincoln': 'sheriff@lincolncounty.mt.gov',
                'Madison': 'sheriff@madisoncounty.mt.gov',
                'McCone': 'sheriff@mcconecounty.mt.gov',
                'Meagher': 'sheriff@meaghercounty.mt.gov',
                'Mineral': 'sheriff@mineralcounty.mt.gov',
                'Missoula': 'sheriff@missoulacounty.mt.gov',
                'Musselshell': 'sheriff@musselshellcounty.mt.gov',
                'Park': 'sheriff@parkcounty.mt.gov',
                'Petroleum': 'sheriff@petroleumcounty.mt.gov',
                'Phillips': 'sheriff@phillipscounty.mt.gov',
                'Pondera': 'sheriff@ponderacounty.mt.gov',
                'Powder River': 'sheriff@powderrivercounty.mt.gov',
                'Powell': 'sheriff@powellcounty.mt.gov',
                'Prairie': 'sheriff@prairiecounty.mt.gov',
                'Ravalli': 'sheriff@ravallicounty.mt.gov',
                'Richland': 'sheriff@richlandcounty.mt.gov',
                'Roosevelt': 'sheriff@rooseveltcounty.mt.gov',
                'Rosebud': 'sheriff@rosebudcounty.mt.gov',
                'Sanders': 'sheriff@sanderscounty.mt.gov',
                'Sheridan': 'sheriff@sheridancounty.mt.gov',
                'Silver Bow': 'sheriff@silverbowcounty.mt.gov',
                'Stillwater': 'sheriff@stillwatercounty.mt.gov',
                'Sweet Grass': 'sheriff@sweetgrasscounty.mt.gov',
                'Teton': 'sheriff@tetoncounty.mt.gov',
                'Toole': 'sheriff@toolecounty.mt.gov',
                'Treasure': 'sheriff@treasurecounty.mt.gov',
                'Valley': 'sheriff@valleycounty.mt.gov',
                'Wheatland': 'sheriff@wheatlandcounty.mt.gov',
                'Wibaux': 'sheriff@wibauxcounty.mt.gov',
                'Yellowstone': 'sheriff@yellowstonecounty.mt.gov'
            }
            
            # Filter emails for selected counties
            recipient_emails = [SHERIFFS_EMAILS[county] for county in counties if county in SHERIFFS_EMAILS]
            
            if not recipient_emails:
                flash('No valid sheriffs emails found for selected counties')
                return redirect(url_for('admin_emails'))
            
            # Send emails
            try:
                from email_worker import EmailWorker
                worker = EmailWorker()
                results = worker.send_bulk_emails(recipient_emails, subject, body)
                
                successful = sum(1 for v in results.values() if v)
                failed = len(results) - successful
                
                flash(f'✅ Emails sent! Success: {successful}/{len(results)}')
                if failed > 0:
                    flash(f'⚠️ Failed to send to {failed} recipients', 'warning')
                
            except Exception as e:
                flash(f'Error sending emails: {str(e)}')
            
            return redirect(url_for('admin_emails'))
    
    return render_template('admin_emails.html', counties=config.MONTANA_COUNTIES)

@app.route('/admin/emails/template/<template_type>')
@login_required
def get_email_template(template_type):
    """Get a preset email template"""
    
    TEMPLATES = {
        'blotter_request': {
            'subject': 'Request for Law Enforcement Blotter Records - Montana Blotter Project',
            'body': '''Dear Sheriff,

We are writing to request law enforcement blotter records from your county as part of the Montana Blotter project, a public information initiative to make law enforcement activity more transparent and accessible to citizens.

The Montana Blotter aggregates public blotter information from sheriffs' offices across the state, allowing citizens to search and view recent law enforcement incidents in their area. This helps communities stay informed about public safety activities.

We would greatly appreciate it if your office could provide regular blotter updates (weekly or daily) via email. The appropriate format would be either:
- PDF documents with incident listings
- CSV/Excel spreadsheets with structured data
- Any other standard format your office uses

All information shared will be made publicly available and properly attributed to your department.

Thank you for your time and consideration. Please contact us if you have any questions about this initiative.

Best regards,
Montana Blotter Project
'''
        },
        'follow_up': {
            'subject': 'Follow-up: Law Enforcement Blotter Submission - Montana Blotter',
            'body': '''Dear Sheriff,

We hope you received our previous request regarding law enforcement blotter records for the Montana Blotter project. We have not yet received a response and wanted to follow up.

The Montana Blotter is a valuable public resource for citizens to stay informed about law enforcement activity in their communities. Your county's participation would be greatly appreciated.

If you have any questions or concerns about the project, please feel free to reach out. We are happy to discuss any data sharing arrangements or requirements your office may have.

Thank you,
Montana Blotter Project
'''
        }
    }
    
    if template_type not in TEMPLATES:
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify(TEMPLATES[template_type])

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == "__main__":
    # Ensure directories exist
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(config.RECORDS_DIR, exist_ok=True)
    
    # Run on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
