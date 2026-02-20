"""
PDF Parser for Montana Sheriff's Office Blotters
Handles GCSO format and adaptable for other counties
"""

import pdfplumber
import re
from datetime import datetime
from typing import List, Dict, Optional

class BlotterParser:
    """Parse police blotter PDFs into structured data"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.county = None
        self.incidents = []
    
    def parse(self) -> Dict:
        """Main parsing method - returns structured data"""
        with pdfplumber.open(self.pdf_path) as pdf:
            # Extract text from all pages
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            
            # Detect county from header
            self.county = self._detect_county(full_text)
            
            # Parse incidents based on format
            if "GCSO" in full_text or "Gallatin County" in full_text:
                self.incidents = self._parse_gcso_format(full_text)
            else:
                self.incidents = self._parse_generic_format(full_text)
        
        return {
            'county': self.county,
            'incidents': self.incidents,
            'total_count': len(self.incidents)
        }
    
    def _detect_county(self, text: str) -> str:
        """Extract county name from PDF header"""
        # Look for common patterns
        county_patterns = [
            r"(\w+)\s+County\s+Sheriff",
            r"GCSO",  # Gallatin County Sheriff's Office
            r"(\w+)\s+County",
        ]
        
        for pattern in county_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern == r"GCSO":
                    return "Gallatin"
                return match.group(1)
        
        return "Unknown"
    
    def _parse_gcso_format(self, text: str) -> List[Dict]:
        """Parse GCSO-specific format with CFS numbers and command logs"""
        incidents = []
        
        # Pattern to find incident blocks
        # GCSO format: MM/DD/YY HH:MM:SS CFS26-XXXXXX LOCATION CODE
        incident_pattern = r'(\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+(CFS\d{2}-\d+)\s+(.+?)\s+(\w+(?:\s+\w+)?)\s*$'
        
        lines = text.split('\n')
        current_incident = None
        command_logs = []
        
        for i, line in enumerate(lines):
            # Skip header lines
            if 'CFS Date/Time' in line or 'Command Log' in line or 'Page' in line:
                continue
            
            # Check if this is a new incident header
            match = re.match(incident_pattern, line.strip())
            if match:
                # Save previous incident if exists
                if current_incident:
                    current_incident['command_logs'] = command_logs
                    current_incident['details'] = self._extract_narrative(command_logs)
                    incidents.append(current_incident)
                
                # Start new incident
                date_time, cfs_num, location, code = match.groups()
                date_parts = date_time.split()
                
                current_incident = {
                    'cfs_number': cfs_num.strip(),
                    'date': date_parts[0],
                    'time': date_parts[1],
                    'location': location.strip(),
                    'incident_type': code.strip(),
                    'officer': None
                }
                command_logs = []
            
            # Check if this is a command log entry
            elif current_incident and re.match(r'\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+-\s+', line):
                # Parse command log: "02/11/26 01:34:33 - Alexander, Logan - Details..."
                log_match = re.match(r'(\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+([\w,\s]+)\s+-\s+(.+)', line)
                if log_match:
                    timestamp, officer, entry = log_match.groups()
                    command_logs.append({
                        'timestamp': timestamp.strip(),
                        'officer': officer.strip(),
                        'entry': entry.strip()
                    })
                    # Set primary officer if not set
                    if not current_incident['officer']:
                        current_incident['officer'] = officer.strip()
        
        # Don't forget the last incident
        if current_incident:
            current_incident['command_logs'] = command_logs
            current_incident['details'] = self._extract_narrative(command_logs)
            incidents.append(current_incident)
        
        return incidents
    
    def _extract_narrative(self, command_logs: List[Dict]) -> str:
        """Extract the main narrative from command logs"""
        if not command_logs:
            return ""
        
        # The narrative is usually the longest entry or entries with actual incident details
        narratives = []
        for log in command_logs:
            entry = log['entry']
            # Skip technical dispatch entries
            if len(entry) > 50 and not any(skip in entry.upper() for skip in ['CB1', 'CB2', 'NO ANSWER', 'VM', 'ADV']):
                narratives.append(entry)
        
        return " ".join(narratives) if narratives else (command_logs[-1]['entry'] if command_logs else "")
    
    def _parse_generic_format(self, text: str) -> List[Dict]:
        """Fallback parser for non-GCSO formats"""
        incidents = []
        
        # Generic date-based parsing
        # Look for lines starting with dates
        lines = text.split('\n')
        
        for line in lines:
            # Match MM/DD/YY or YYYY-MM-DD at start of line
            date_match = re.match(r'^(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})', line)
            if date_match:
                date = date_match.group(1)
                rest = line[len(date):].strip()
                
                # Try to extract incident type and details
                parts = rest.split('-', 1)
                if len(parts) >= 2:
                    incident_type = parts[0].strip()
                    details = parts[1].strip()
                else:
                    incident_type = "Unknown"
                    details = rest
                
                incidents.append({
                    'cfs_number': None,
                    'date': date,
                    'time': None,
                    'location': "Unknown",
                    'incident_type': incident_type,
                    'details': details,
                    'officer': None,
                    'command_logs': []
                })
        
        return incidents


def test_parser(pdf_path: str):
    """Test the parser with a PDF file"""
    parser = BlotterParser(pdf_path)
    result = parser.parse()
    
    print(f"\n{'='*60}")
    print(f"County: {result['county']}")
    print(f"Total Incidents: {result['total_count']}")
    print(f"{'='*60}\n")
    
    for i, incident in enumerate(result['incidents'][:5], 1):  # Show first 5
        print(f"Incident #{i}")
        print(f"  CFS: {incident.get('cfs_number', 'N/A')}")
        print(f"  Date/Time: {incident['date']} {incident.get('time', '')}")
        print(f"  Type: {incident['incident_type']}")
        print(f"  Location: {incident.get('location', 'N/A')}")
        print(f"  Officer: {incident.get('officer', 'N/A')}")
        print(f"  Details: {incident['details'][:100]}...")
        print(f"  Command Logs: {len(incident.get('command_logs', []))} entries")
        print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_parser(sys.argv[1])
    else:
        print("Usage: python pdf_parser.py <path_to_pdf>")
