#!/bin/bash
set -euo pipefail

DB_PATH="/root/montanablotter/blotter.db"
BACKUP_DIR="/root/montanablotter/db_backups"
BUCKET="s3://montanablotter-backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/blotter_$TIMESTAMP.db.gz"
LOG="/root/montanablotter/backup.log"

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..." >> "$LOG"

# Use SQLite's backup API via .dump to get a consistent snapshot
sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/blotter_$TIMESTAMP.db"
gzip "$BACKUP_DIR/blotter_$TIMESTAMP.db"

# Upload to S3
aws s3 cp "$BACKUP_FILE" "$BUCKET/$(basename "$BACKUP_FILE")" >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Uploaded $(basename "$BACKUP_FILE") to $BUCKET" >> "$LOG"

# Remove local backup copies older than 7 days
find "$BACKUP_DIR" -name "blotter_*.db.gz" -mtime +7 -delete

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"
