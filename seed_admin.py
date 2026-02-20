"""
Seed Admin User
Creates or updates the admin user with proper bcrypt hashing
"""

import sqlite3
from flask_bcrypt import Bcrypt
from flask import Flask
import config

# Create dummy app for Bcrypt
app = Flask(__name__)
bcrypt = Bcrypt(app)

def seed_admin(username='admin', password='Blotter2026!'):
    """Create or update admin user"""
    
    # Generate hashed password
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        # Check if admin exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user:
            # Update existing admin
            cursor.execute(
                "UPDATE users SET password = ?, membership = 'pro' WHERE username = ?",
                (hashed_pw, username)
            )
            print(f"✅ Admin user '{username}' updated with new password")
        else:
            # Create new admin
            cursor.execute(
                "INSERT INTO users (username, password, membership) VALUES (?, ?, ?)",
                (username, hashed_pw, 'pro')
            )
            print(f"✅ Admin user '{username}' created")
        
        conn.commit()
        conn.close()
        
        print(f"\nLogin credentials:")
        print(f"  Username: {username}")
        print(f"  Password: {password}")
        print(f"  Membership: pro")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        seed_admin(sys.argv[1], sys.argv[2])
    else:
        seed_admin()
        print("\nTo create custom admin: python seed_admin.py <username> <password>")
