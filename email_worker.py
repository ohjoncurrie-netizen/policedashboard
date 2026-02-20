"""
Email Worker - Fetches blotter PDFs from IONOS email and processes them
Unified version replacing email_worker.py and fetch_mail.py
"""

import imaplib
import email
import os
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
from processor import process_new_blotter, process_text_blotter

# Setup logging
logging.basicConfig(
    filename=config.LOG_FILE,
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)

class EmailWorker:
    """Handles fetching and processing blotter emails"""
    
    def __init__(self):
        self.email_user = config.EMAIL_USER
        self.email_pass = config.EMAIL_PASSWORD
        self.imap_server = config.IMAP_SERVER
        self.imap_port = config.IMAP_PORT
        self.upload_dir = config.UPLOAD_DIR
        self.processed_folder = config.PROCESSED_FOLDER
        
        # Ensure upload directory exists
        os.makedirs(self.upload_dir, exist_ok=True)
    
    def fetch_and_process_emails(self):
        """Main method - fetch emails and process PDFs"""
        try:
            # Connect to IONOS IMAP
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_user, self.email_pass)
            mail.select("INBOX")
            
            logging.info("Connected to IONOS IMAP successfully")
            
            # Search all unread emails
            status, messages = mail.search(None, 'UNSEEN')

            if status != 'OK' or not messages[0]:
                logging.info("No new emails found")
                mail.logout()
                return 0

            email_ids = messages[0].split()
            logging.info(f"Found {len(email_ids)} unread emails to scan")
            
            processed_count = 0
            
            for num in email_ids:
                try:
                    # Fetch the email
                    res, msg_data = mail.fetch(num, "(RFC822)")
                    
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Extract subject for logging
                            subject = msg.get('subject', 'No Subject')
                            sender = msg.get('from', 'Unknown')
                            logging.info(f"Processing email: {subject} from {sender}")

                            # Skip bounce / delivery-failure emails
                            if 'mailer-daemon' in sender.lower() or 'delivery' in subject.lower():
                                logging.info(f"Skipping bounce/delivery email: {subject}")
                                continue

                            # Process attachments
                            had_pdf, pdf_succeeded = self._process_attachments(msg)

                            if had_pdf:
                                # Email had PDF(s) — mark processed regardless of parse errors
                                if pdf_succeeded:
                                    self._move_to_processed(mail, num)
                                    processed_count += 1
                                    logging.info("Successfully processed email with PDF(s)")
                                else:
                                    logging.error(f"PDF(s) found but all failed to process: {subject}")
                            else:
                                # No PDF — try plain-text body as blotter
                                body = self._extract_body_text(msg)
                                if body and len(body.strip()) > 200:
                                    try:
                                        process_text_blotter(body, sender_email=sender)
                                        self._move_to_processed(mail, num)
                                        processed_count += 1
                                        logging.info("Processed text-body blotter from email")
                                    except Exception as e:
                                        logging.error(f"Failed to process text blotter: {e}")
                                else:
                                    logging.info(f"No blotter content found in email: {subject} — skipping")
                
                except Exception as e:
                    logging.error(f"Error processing email {num}: {str(e)}")
                    continue
            
            mail.expunge()
            mail.logout()
            
            logging.info(f"Email worker complete: {processed_count} emails processed")
            return processed_count
            
        except imaplib.IMAP4.error as e:
            logging.error(f"IMAP Error: {str(e)}")
            return 0
        except Exception as e:
            logging.error(f"Email worker critical error: {str(e)}")
            return 0
    
    def _process_attachments(self, msg) -> tuple[bool, bool]:
        """
        Extract and process PDF attachments from email.
        Returns (had_pdf, any_succeeded):
          had_pdf      — True if at least one .pdf attachment was found
          any_succeeded — True if at least one was successfully processed
        """
        had_pdf = False
        any_succeeded = False

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if filename and filename.lower().endswith('.pdf'):
                had_pdf = True
                filepath = os.path.join(self.upload_dir, filename)

                with open(filepath, 'wb') as f:
                    f.write(part.get_payload(decode=True))

                logging.info(f"Saved PDF: {filename}")

                try:
                    batch_id = process_new_blotter(filepath)
                    logging.info(f"Processed PDF: {filename} -> Batch #{batch_id}")
                    any_succeeded = True
                except Exception as e:
                    logging.error(f"Failed to process PDF {filename}: {str(e)}")

        return had_pdf, any_succeeded

    def _extract_body_text(self, msg) -> str:
        """Extract plain text from email body. Prefers text/plain, falls back to stripped text/html."""
        plain = None
        html = None

        for part in msg.walk():
            content_type = part.get_content_type()
            if part.get_content_maintype() == 'multipart':
                continue
            if content_type == 'text/plain' and plain is None:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
            elif content_type == 'text/html' and html is None:
                payload = part.get_payload(decode=True)
                if payload:
                    raw_html = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                    # Strip tags with a simple regex for fallback purposes
                    import re as _re
                    html = _re.sub(r'<[^>]+>', ' ', raw_html)
                    html = _re.sub(r'\s+', ' ', html).strip()

        return plain if plain is not None else (html or "")
    
    def _move_to_processed(self, mail, email_num):
        """Move processed email to Processed folder"""
        try:
            # Try to create folder if it doesn't exist
            mail.create(self.processed_folder)
        except:
            pass  # Folder probably already exists
        
        try:
            # Copy to Processed folder
            mail.copy(email_num, self.processed_folder)
            # Mark for deletion from inbox
            mail.store(email_num, '+FLAGS', '\\Deleted')
        except Exception as e:
            logging.warning(f"Could not move email to Processed folder: {e}")
    
    def send_email(self, to_address, subject, body, html_body=None):
        """Send an email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_user
            msg['To'] = to_address
            msg['Subject'] = subject
            
            # Attach plain text version
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach HTML version if provided
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            
            # Connect to SMTP server
            smtp = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
            smtp.starttls()
            smtp.login(self.email_user, self.email_pass)
            
            # Send email
            smtp.sendmail(self.email_user, to_address, msg.as_string())
            smtp.quit()
            
            logging.info(f"Email sent successfully to {to_address}")
            return True
        
        except Exception as e:
            logging.error(f"Error sending email to {to_address}: {str(e)}")
            return False
    
    def send_bulk_emails(self, recipients, subject, body, html_body=None):
        """Send email to multiple recipients"""
        results = {}
        for recipient in recipients:
            results[recipient] = self.send_email(recipient, subject, body, html_body)
        return results


def run_worker():
    """Run the email worker once"""
    worker = EmailWorker()
    count = worker.fetch_and_process_emails()
    print(f"Processed {count} emails")
    return count


if __name__ == "__main__":
    run_worker()
