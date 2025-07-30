import pdfplumber
import re
from typing import Optional, Tuple

def extract_date_from_citation_pdf(pdf_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Reads the first 10 lines of the PDF, checks for 'section', and extracts a last updated date if present.
    Returns: (date_string, full_text)
    """
    lines = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                page_lines = text.splitlines()
                for line in page_lines:
                    lines.append(line)
                    if len(lines) >= 10:
                        break
                if len(lines) >= 10:
                    break
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return None, None
    
    joined_text = '\n'.join(lines)
    if not any('section' in line.lower() for line in lines):
        return None, joined_text
    # Try to extract a date (flexible pattern: dd-mm-yyyy, dd/mm/yyyy, yyyy-mm-dd, dd Month yyyy, etc.)
    date_patterns = [
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',
        r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',
        r'\b(\d{1,2} [A-Za-z]+ \d{4})\b',
        r'Last updated[:\s]*([\w\s,/-]+\d{4})',
        r'Updated on[:\s]*([\w\s,/-]+\d{4})',
    ]
    for pattern in date_patterns:
        m = re.search(pattern, joined_text, re.IGNORECASE)
        if m:
            return m.group(1).strip(), joined_text
    return None, joined_text
