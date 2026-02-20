"""
Processor - Handles PDF parsing and database insertion
Replaces the old processor.py with actual parsing logic
"""

import sqlite3
import os
import logging
from pdf_parser import BlotterParser

DB_PATH = '/root/montanablotter/blotter.db'
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_new_blotter(pdf_path: str, county: str = None) -> int:
    """
    Process a new blotter PDF file
    
    Args:
        pdf_path: Path to the PDF file
        county: Optional county name (will be auto-detected if not provided)
    
    Returns:
        batch_id: The ID of the created blotter batch
    """
    
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    logging.info(f"Processing blotter: {pdf_path}")
    
    # Step 1: Parse the PDF
    try:
        parser = BlotterParser(pdf_path)
        result = parser.parse()
    except Exception as e:
        logging.error(f"Failed to parse PDF: {e}")
        raise
    
    # Use detected county if not provided
    if not county:
        county = result['county']
    
    logging.info(f"Detected county: {county}, Found {result['total_count']} incidents")
    
    # Step 2: Insert into database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create the Batch Entry
        cursor.execute(
            'INSERT INTO blotters (filename, county, incident_count, file_path) VALUES (?, ?, ?, ?)', 
            (os.path.basename(pdf_path), county, result['total_count'], pdf_path)
        )
        batch_id = cursor.lastrowid
        logging.info(f"Created blotter batch #{batch_id}")
        
        # Insert individual incidents
        for incident in result['incidents']:
            cursor.execute('''
                INSERT INTO records (
                    blotter_id, cfs_number, date, time, incident_type, 
                    location, details, county, officer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                incident.get('cfs_number'),
                incident.get('date'),
                incident.get('time'),
                incident.get('incident_type'),
                incident.get('location'),
                incident.get('details'),
                county,
                incident.get('officer')
            ))
            record_id = cursor.lastrowid
            
            # Insert command logs if available
            for log in incident.get('command_logs', []):
                cursor.execute('''
                    INSERT INTO command_logs (record_id, timestamp, officer, entry)
                    VALUES (?, ?, ?, ?)
                ''', (record_id, log.get('timestamp'), log.get('officer'), log.get('entry')))
        
        conn.commit()
        logging.info(f"✅ Batch #{batch_id} complete: {result['total_count']} incidents indexed")
        
        return batch_id
        
    except Exception as e:
        conn.rollback()
        logging.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def update_web_data(pdf_path: str):
    """
    Legacy function name for compatibility with email_worker.py
    Calls process_new_blotter internally
    """
    return process_new_blotter(pdf_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        pdf = sys.argv[1]
        county = sys.argv[2] if len(sys.argv) > 2 else None
        batch_id = process_new_blotter(pdf, county)
        print(f"Successfully processed blotter. Batch ID: {batch_id}")
    else:
        print("Usage: python processor.py <pdf_path> [county_name]")
