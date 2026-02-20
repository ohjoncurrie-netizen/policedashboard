# Montana Blotter - Police Blotter Aggregation Platform

A free, open-source platform for aggregating and publishing Montana's public police blotters from all 56 counties.

## 🎯 Project Overview

Montana Blotter (`montanablotter.com` / `fertherecerd.com`) provides centralized access to "For the Record" police blotters, incident summaries, arrests, and citations published by Montana sheriff offices.

## 🏗️ System Architecture

### Technology Stack
- **Backend**: Python Flask
- **Database**: SQLite
- **PDF Processing**: pdfplumber
- **Authentication**: Flask-Login + Bcrypt
- **Web Server**: Nginx + Gunicorn
- **Email**: IMAP (IONOS)

### Core Components

1. **PDF Parser** (`pdf_parser.py`)
   - Extracts structured data from sheriff office PDFs
   - Handles GCSO format and generic formats
   - Parses CFS numbers, dates, locations, incident types
   - Extracts command logs and narratives

2. **Processor** (`processor.py`)
   - Orchestrates PDF parsing
   - Inserts data into database
   - Creates batch records for tracking

3. **Email Worker** (`email_worker.py`)
   - Fetches PDFs from IONOS email (IMAP)
   - Processes attachments automatically
   - Moves processed emails to "Processed" folder

4. **Flask Application** (`app.py`)
   - User authentication and dashboard
   - Blotter browsing and search
   - County filtering
   - Admin interface for manual uploads

5. **Database** (`init_db.py`)
   - SQLite with 4 main tables:
     - `users` - Authentication
     - `blotters` - PDF batch tracking
     - `records` - Individual incidents
     - `command_logs` - Detailed event timelines

## 📊 Database Schema

```
users
├── id (PRIMARY KEY)
├── username (UNIQUE)
├── password (bcrypt hashed)
├── email
├── membership (free/pro)
└── created_at

blotters
├── id (PRIMARY KEY)
├── filename
├── county
├── upload_date
├── incident_count
├── status
├── file_path
└── notes

records
├── id (PRIMARY KEY)
├── blotter_id (FOREIGN KEY)
├── cfs_number
├── date
├── time
├── incident_type
├── location
├── details
├── county
├── officer
└── created_at

command_logs
├── id (PRIMARY KEY)
├── record_id (FOREIGN KEY)
├── timestamp
├── officer
├── entry
└── created_at
```

## 🚀 Installation & Setup

### Prerequisites
- Python 3.7+
- pip3
- Nginx
- Root access to VPS

### Quick Install

```bash
# 1. Upload files to your VPS
cd /root/montanablotter
# Upload all .py files

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Run automated setup
python3 setup.py

# 4. Configure your credentials
nano config.py
# Update EMAIL_USER, EMAIL_PASSWORD, SECRET_KEY

# 5. Test the system
python3 pdf_parser.py uploads/your_file.pdf
python3 app.py
```

### Manual Setup

See `DEPLOYMENT_GUIDE.py` for detailed step-by-step instructions.

## 🔧 Configuration

Edit `config.py` to customize:

```python
# Email Settings
EMAIL_USER = "juan@fertherecerd.com"
EMAIL_PASSWORD = "your_password"
IMAP_SERVER = "imap.ionos.com"

# Database
DB_PATH = '/root/montanablotter/blotter.db'

# Flask
SECRET_KEY = 'change_this_to_random_string'
HOST = '0.0.0.0'
PORT = 80
```

## 📧 Email Processing

The system automatically fetches PDFs from your email:

1. Sheriff offices send blotters to your email
2. Email worker (cron job) checks inbox every 15 minutes
3. PDFs are extracted and saved
4. Processor parses and inserts into database
5. Processed emails moved to "Processed" folder

### Setting up Email Automation

```bash
# Add cron job
crontab -e

# Add this line (runs every 15 minutes)
*/15 * * * * cd /root/montanablotter && /usr/bin/python3 email_worker.py >> /root/montanablotter/cron.log 2>&1
```

## 🎨 Dashboard Features

- **Authentication**: Secure login system
- **Browse Blotters**: View all processed PDFs by county
- **Search**: Find specific incidents
- **Filter**: By county, date, incident type
- **Detail View**: See full command logs for each incident
- **Admin Upload**: Manual PDF upload for testing

## 📝 Usage Examples

### Process a PDF Manually
```bash
python3 processor.py uploads/gallatin_blotter.pdf Gallatin
```

### Test PDF Parser
```bash
python3 pdf_parser.py uploads/your_file.pdf
```

### Run Email Worker
```bash
python3 email_worker.py
```

### Create Admin User
```bash
python3 seed_admin.py myusername mypassword
```

### Query Database
```bash
sqlite3 blotter.db "SELECT COUNT(*) FROM records;"
sqlite3 blotter.db "SELECT * FROM blotters ORDER BY upload_date DESC LIMIT 5;"
```

## 🔍 PDF Format Support

### Currently Supported:
- **GCSO Format** (Gallatin County Sheriff's Office)
  - CFS numbers
  - Command logs
  - Timestamps
  - Officer names
  - Incident types

### Generic Format:
- Date-based parsing
- Incident type extraction
- Basic details

### Adding New Formats:
Modify `pdf_parser.py` → `_parse_generic_format()` or add new county-specific method.

## 🛠️ Troubleshooting

### Database Locked
```bash
# Find process using database
ps aux | grep python
kill <pid>
```

### PDF Parsing Issues
```bash
# Test parser
python3 pdf_parser.py path/to/pdf.pdf
# Check output for errors
```

### Email Worker Not Running
```bash
# Test manually
python3 email_worker.py
# Check logs
tail -f worker.log
```

### Can't Login
```bash
# Reset admin password
python3 seed_admin.py admin NewPassword123
```

## 📂 File Structure

```
/root/montanablotter/
├── app.py                  # Flask application
├── config.py               # Configuration
├── init_db.py             # Database initialization
├── pdf_parser.py          # PDF parsing logic
├── processor.py           # Processing pipeline
├── email_worker.py        # Email fetching
├── seed_admin.py          # Admin user management
├── setup.py               # Automated setup
├── DEPLOYMENT_GUIDE.py    # Detailed guide
├── requirements.txt       # Python dependencies
├── blotter.db            # SQLite database
├── uploads/              # Incoming PDFs
├── records/              # Processed records
├── templates/            # HTML templates
└── static/               # CSS/JS assets
```

## 🔐 Security Recommendations

1. **Change SECRET_KEY** in config.py
2. **Use environment variables** for credentials
3. **Set file permissions**: `chmod 600 config.py`
4. **Use HTTPS** (Let's Encrypt)
5. **Regular backups** of database
6. **Update dependencies** regularly

## 📊 Monitoring & Logs

```bash
# Application logs
journalctl -u montanablotter -f

# Email worker logs
tail -f worker.log

# Nginx logs
tail -f /var/log/nginx/error.log

# Cron job logs
tail -f cron.log
```

## 🤝 Contributing

This is an open-source project. Contributions welcome!

Areas for improvement:
- Additional county format parsers
- Advanced search features
- Data visualization
- Mobile app
- API endpoints
- Export functionality

## 📜 License

Open source - Free for public use

## 📞 Contact

- Email: juan@fertherecerd.com
- Website: www.fertherecerd.com
- Location: Gibson Flats, MT

## 🗺️ Montana Counties Supported

All 56 Montana counties can be supported. Currently parsing:
- Gallatin County (GCSO format)
- Generic format (fallback for others)

## 🎯 Roadmap

- [ ] Add parsers for more county formats
- [ ] Implement data visualization dashboard
- [ ] Create public API
- [ ] Mobile app development
- [ ] Email notifications for new blotters
- [ ] Advanced analytics
- [ ] Export to CSV/PDF
- [ ] User registration system

---

**Version**: 2.0  
**Last Updated**: February 2026  
**Status**: Production Ready
