"""
MONTANA BLOTTER - DEPLOYMENT GUIDE
===================================

This guide will help you set up and deploy the Montana Blotter system.

STEP 1: BACKUP YOUR CURRENT SYSTEM
-----------------------------------
cd /root/montanablotter
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz *.py blotter.db


STEP 2: UPLOAD NEW FILES TO YOUR VPS
-------------------------------------
Upload these files to /root/montanablotter/:
- init_db.py
- pdf_parser.py
- processor.py
- config.py
- app.py
- email_worker.py
- seed_admin.py


STEP 3: INITIALIZE THE DATABASE
--------------------------------
cd /root/montanablotter
python3 init_db.py

This will:
- Create a backup of your existing database
- Create all necessary tables
- Set up indexes for performance


STEP 4: CREATE ADMIN USER
--------------------------
python3 seed_admin.py

Default credentials:
  Username: admin
  Password: Blotter2026!

Or create custom admin:
  python3 seed_admin.py myusername mypassword


STEP 5: TEST PDF PARSING
-------------------------
# Test with your uploaded PDF
python3 pdf_parser.py uploads/your_file.pdf

# This should show:
# - Detected county
# - Number of incidents found
# - Sample incidents with details


STEP 6: TEST THE PROCESSOR
---------------------------
python3 processor.py uploads/your_file.pdf Gallatin

# This should:
# - Parse the PDF
# - Insert data into database
# - Return a batch ID


STEP 7: UPDATE NGINX CONFIGURATION
-----------------------------------
Your nginx config should point to the Flask app.
If using gunicorn:

# /etc/nginx/sites-available/montanablotter.com
server {
    listen 80;
    server_name montanablotter.com www.montanablotter.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /static {
        alias /root/montanablotter/static;
    }
}


STEP 8: SET UP GUNICORN
-----------------------
Install gunicorn if not installed:
  pip3 install gunicorn

Create systemd service:
  sudo nano /etc/systemd/system/montanablotter.service

Paste this:
```
[Unit]
Description=Montana Blotter Flask App
After=network.target

[Service]
User=root
WorkingDirectory=/root/montanablotter
ExecStart=/usr/bin/python3 -m gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
  sudo systemctl daemon-reload
  sudo systemctl enable montanablotter
  sudo systemctl start montanablotter
  sudo systemctl status montanablotter


STEP 9: SET UP AUTOMATED EMAIL CHECKING
----------------------------------------
Create cron job to check emails every 15 minutes:
  crontab -e

Add this line:
  */15 * * * * cd /root/montanablotter && /usr/bin/python3 email_worker.py >> /root/montanablotter/cron.log 2>&1

Or run manually:
  cd /root/montanablotter
  python3 email_worker.py


STEP 10: SECURITY HARDENING
----------------------------
1. Change the SECRET_KEY in config.py to a random string
2. Move credentials to environment variables (optional):

   # In ~/.bashrc
   export MB_EMAIL_PASSWORD="your_password_here"
   
   # In config.py
   EMAIL_PASSWORD = os.getenv('MB_EMAIL_PASSWORD', 'fallback')

3. Set proper file permissions:
   chmod 600 config.py
   chmod 700 /root/montanablotter


VERIFICATION CHECKLIST
----------------------
[ ] Database initialized successfully
[ ] Admin user created and can login
[ ] PDF parser extracts incidents correctly
[ ] Processor inserts data into database
[ ] Flask app starts without errors
[ ] Nginx proxies requests correctly
[ ] Dashboard displays blotters and records
[ ] Email worker fetches and processes PDFs
[ ] Cron job runs automatically


TROUBLESHOOTING
---------------

Problem: Database locked error
Solution: Make sure no other process is using the database
  ps aux | grep python
  kill <pid> if needed

Problem: PDF parsing returns empty results
Solution: Check the PDF format
  python3 pdf_parser.py path/to/pdf.pdf
  
Problem: Email worker not fetching emails
Solution: Check IONOS credentials in config.py
  Test manually: python3 email_worker.py

Problem: Can't login to dashboard
Solution: Reset admin password
  python3 seed_admin.py admin NewPassword123

Problem: Nginx 502 Bad Gateway
Solution: Check if gunicorn is running
  sudo systemctl status montanablotter
  sudo systemctl restart montanablotter


MONITORING
----------
View logs:
  tail -f /root/montanablotter/worker.log    # Email worker
  tail -f /var/log/nginx/error.log           # Nginx errors
  journalctl -u montanablotter -f            # Flask app
  tail -f /root/montanablotter/cron.log      # Cron job output


USEFUL COMMANDS
---------------
# Restart Flask app
sudo systemctl restart montanablotter

# Check database
sqlite3 /root/montanablotter/blotter.db "SELECT COUNT(*) FROM records;"

# Manually process a PDF
python3 processor.py uploads/newfile.pdf CountyName

# Test email worker
python3 email_worker.py

# View recent blotters
sqlite3 /root/montanablotter/blotter.db "SELECT * FROM blotters ORDER BY upload_date DESC LIMIT 5;"
"""

if __name__ == "__main__":
    print(__doc__)
