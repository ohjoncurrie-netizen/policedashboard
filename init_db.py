"""
Database Schema Initialization for Montana Blotter
Creates all necessary tables with proper structure
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = '/root/montanablotter/blotter.db'

def init_database():
    """Initialize the database with all required tables"""
    
    # Backup existing database if it exists
    if os.path.exists(DB_PATH):
        backup_path = f'{DB_PATH}.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        print(f"⚠️  Backing up existing database to: {backup_path}")
        os.system(f'cp {DB_PATH} {backup_path}')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # --- USERS TABLE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            membership TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # --- BLOTTERS TABLE (Batch/File level) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blotters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            county TEXT NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            incident_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'processed',
            file_path TEXT,
            notes TEXT
        )
    ''')
    
    # --- RECORDS TABLE (Individual incidents) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blotter_id INTEGER NOT NULL,
            cfs_number TEXT,
            date TEXT NOT NULL,
            time TEXT,
            incident_type TEXT,
            location TEXT,
            details TEXT,
            county TEXT NOT NULL,
            officer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (blotter_id) REFERENCES blotters(id) ON DELETE CASCADE
        )
    ''')
    
    # --- COMMAND LOGS TABLE (Detailed chronological entries for each incident) ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            timestamp TEXT,
            officer TEXT,
            entry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
        )
    ''')
    
    # --- Create indexes for better query performance ---
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_county ON records(county)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_records_blotter ON records(blotter_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blotters_county ON blotters(county)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blotters_date ON blotters(upload_date)')
    
    conn.commit()
    conn.close()
    
    print("✅ Database initialized successfully!")
    print(f"📁 Location: {DB_PATH}")
    print("\nTables created:")
    print("  - users (authentication)")
    print("  - blotters (PDF batch tracking)")
    print("  - records (individual incidents)")
    print("  - command_logs (detailed event logs)")

if __name__ == "__main__":
    init_database()
