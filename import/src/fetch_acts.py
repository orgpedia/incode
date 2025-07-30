import json
from pydantic import BaseModel
from typing import List, Tuple, Optional
from pathlib import Path
import sys
import time
import subprocess
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import pdfplumber
import re

def extract_date_from_citation_pdf(pdf_path: str):
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

    # Case 1: Look for 'As modified upto' or 'As modified up to' (with optional spaces, case-insensitive)
    for line in lines:
        l = line.lower().replace('  ', ' ')
        if 'as modified upto' in l or 'as modified up to' in l:
            # Regex for these patterns
            # Handles: (As modified upto the 28th January, 2019), (As modified up to the 12 th December 2012), etc.
            match = re.search(r'(?:as modified up\s*to|as modified upto)\s*\(?\s*the\s*(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:of\s*)?([A-Za-z]+),?\s*(\d{4})', l)
            if match:
                day = match.group(1)
                month = match.group(2).capitalize()
                year = match.group(3)
                return f"{day} {month} {year}", lines
    # Case 2: Look for a line with 'Text as on '
    for line in lines:
        if 'text as on ' in line.lower():
            # Extract everything after 'Text as on '
            idx = line.lower().find('text as on ')
            date_portion = line[idx + len('text as on '):].strip('[]').strip()
            # Try to extract a date from the remainder
            # e.g. '7th June 2024' or '7 June 2024'
            date_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})', date_portion)
            if date_match:
                # Normalize date to 'DD Month YYYY'
                day = date_match.group(1)
                month = date_match.group(2)
                year = date_match.group(3)
                return f"{day} {month} {year}", lines
            # Fallback: just return the portion after 'Text as on '
            return date_portion, lines
    # If not found, fall back to old patterns
    return None, lines


class ChapterInfo(BaseModel):
    number: str
    title: str
    chapter_id: Optional[str]
    sub_chapters: List[Tuple[str,str]]
    sections: List[List[str]]


class SectionInfo(BaseModel):
    web_number: str
    number: str
    title: str
    url: str
    has_notification: bool


class ActDetails(BaseModel):
    url: str
    web_number: str
    web_act_id: str
    chapters: List[ChapterInfo]
    sections: List[SectionInfo]
    pdf_urls: List[str]
    citation_pdf_urls: List[str] = []

def fetch_page_curl(url):
    # use curl to fetch the page
    time.sleep(2)
    response = subprocess.check_output(['curl', url])
    return response.decode('utf-8')

def fetch_pdf(url, output_path):
    """Download a PDF file from URL using requests library.

    Args:
        url: The URL of the PDF to download
        output_path: path to save the PDF.

    Returns:
        If output_path is None, returns the binary content of the PDF.
        If output_path is provided, returns True if download was successful, False otherwise.
    """
    import os
    import requests
    from pathlib import Path

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-IN,en-GB;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }

    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        # If output_path is provided, save to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading PDF from {url}: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error downloading PDF: {str(e)}")
        return False

Browser = None
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
}
def fetch_page_playwright(url, max_retries=1):
    """Fetch page content using Playwright with retries and error handling.

    Args:
        url: The URL to fetch
        max_retries: Maximum number of retry attempts

    Returns:
        str: The page HTML content or None if all retries fail
    """
    from playwright.sync_api import sync_playwright

    for attempt in range(max_retries):
        playwright = None
        browser = None
        context = None
        page = None

        try:
            # Start Playwright
            playwright = sync_playwright().start()

            # Launch browser
            browser = playwright.chromium.launch(headless=False)

            # Create a new context with custom headers
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=HEADERS['User-Agent']
            )

            # Create a new page
            page = context.new_page()

            # import pdb
            # pdb.set_trace()

            # Set extra HTTP headers
            # page.set_extra_http_headers({
            #     k: v for k, v in HEADERS.items()
            #     if k.lower() not in ['host', 'content-length', 'connection']
            # })

            # Navigate to the URL with a 60-second timeout
            response = page.goto(
                url,
                wait_until='domcontentloaded',
                timeout=60000
            )

            # Check if the response was successful
            if not response.ok:
                raise Exception(f"HTTP {response.status} for {url}")

            # Wait for network to be idle
            page.wait_for_load_state('networkidle')

            # Get the HTML content
            html = page.content()

            # Clean up resources
            page.close()
            context.close()
            browser.close()
            playwright.stop()

            return html

        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {url}: {str(e)}")

            if attempt == max_retries - 1:  # Last attempt
                print(f"Failed to fetch {url} after {max_retries} attempts")
                return None

            # Clean up resources before retry
            try:
                if page:
                    page.close()
                if context:
                    context.close()
                if browser:
                    browser.close()
                if playwright:
                    playwright.stop()
            except Exception as cleanup_error:
                print(f"Error during cleanup: {str(cleanup_error)}")

            # Exponential backoff
            time.sleep(2 ** attempt)

def close_browser():
    global Browser
    if Browser is not None:
        Browser.close()
        Browser = None

def fetch_section(web_act_id, section_info, section_dir: Path):
    """Fetch section content with error handling and retries."""
    section_html_path = section_dir / f'{section_info.web_number}.html'

    # Return cached content if exists
    if section_html_path.exists():
        print(f'\tSection: {section_info.web_number}: already exists')
        return section_html_path.read_text()

    print(f'\tSection: {section_info.web_number}: fetching...')

    # Fetch main section content
    section_xhr_url = f'https://www.indiacode.nic.in/SectionPageContent?&actid={web_act_id}&sectionID={section_info.web_number}'
    section_xhr_str = fetch_page_playwright(section_xhr_url)

    if section_xhr_str is None:
        print(f'\tFailed to fetch section {section_info.web_number}')
        return None

    # Save the section content
    section_html_path.write_text(section_xhr_str)

    # Handle notifications if they exist
    if section_info.has_notification:
        try:
            notification_url = f'https://www.indiacode.nic.in/SectionPageContent?&actid={web_act_id}&sectionID={section_info.web_number}&orgactid={web_act_id}'
            notification_xhr_str = fetch_page_playwright(notification_url)

            if notification_xhr_str:
                notification_html_path = section_dir / f'{section_info.web_number}_notification.html'
                notification_html_path.write_text(notification_xhr_str)
            else:
                print(f'\tFailed to fetch notification for section {section_info.web_number}')

        except Exception as e:
            print(f'\tError fetching notification for section {section_info.web_number}: {str(e)}')

    return section_xhr_str


def fetch_act(act_url, act_web_number, website_dir: Path):
    # Load HTML file
    act_dir = website_dir / act_web_number
    act_dir.mkdir(exist_ok=True, parents=True)

    html_path = act_dir / f'{act_web_number}.html'
    json_path = act_dir / f'{act_web_number}.json'

    # if json_path.exists():
    #     print(f'{act_web_number}: already exists')
    #     return ActDetails(**json.loads(json_path.read_text()))

    if html_path.exists():
        html_str = html_path.read_text()
    else:
        html_str = fetch_page_playwright(act_url)
        html_path.write_text(html_str)

    from lxml import etree
    parser = etree.HTMLParser()
    tree = etree.fromstring(html_str, parser)

    # --- Extract Chapters ---
    chapters = []
    # Find the div with class 'col-sm-4' inside the 'tb1' tab
    col_divs = tree.xpath('//div[contains(@class, "col-sm-4")]')
    if col_divs:
        col_div = col_divs[0]
        li_nodes = col_div.xpath('./li')
    else:
        li_nodes = []

    chapter_sections = []
    for idx, li in enumerate(li_nodes):
        number_elem = li.xpath('./b/text()')
        number = number_elem[0].strip() if number_elem else None
        print('Chapter: ', number)
        if not number:
            print('\tChapter number not found')
            continue

        # Get first <ul><li>
        inner_li = li.xpath('./ul/li')[0]

        # CASE 1: Single chapter with <a class="headingtwo">
        a_tag = inner_li.xpath('./a[@class="headingtwo"]')
        if a_tag:
            title = a_tag[0].text.strip()
            chapter_id = a_tag[0].get('id')
            sub_chapters = []

        else:
            title_text = inner_li.xpath('text()')
            title = title_text[0].strip() if title_text else None
            chapter_id = None

            sub_chapters = [
                (a.get('id'), a.text.strip())
                for a in inner_li.xpath('./ul/li/a[@class="headingthree"]')
            ]

        chapters.append(ChapterInfo(number=number, title=title, chapter_id=chapter_id, sub_chapters=sub_chapters, sections=chapter_sections))

    # --- Extract Sections ---
    # print(etree.tostring(content_div, encoding="unicode", pretty_print=True))
    sections, web_act_id = [], ''
    section_nodes = tree.xpath('//table[@id="myTableActSection"]//a[@class="title"]')

    for idx, sec in enumerate(section_nodes):
        sec_id = sec.attrib.get("id", "")
        web_act_id = sec_id.split('#')[0]
        web_number = sec_id.split('#')[1]
        href = sec.attrib.get("href", "")
        sec_url = href if href.startswith("http") else ("https://www.indiacode.nic.in" + href)
        number = sec.find('span').text.strip()
        title = sec.find('span').tail.strip()
        span_class = sec.xpath('./span')[0].get('class', '')
        has_notification = 'label-default' in span_class
        sections.append(SectionInfo(web_number=web_number, number=number, title=title, url=sec_url, has_notification=has_notification))

    # Extract PDF links
    citation_pdf_urls, pdf_urls = extract_pdf_links(tree)
    assert len(citation_pdf_urls) <= 1

    # filter out pdf_urls that are already covered in citation_pdf_urls,
    # don't do exact match, but match the path component of url, returned by urlparse
    citation_pdf_path = urlparse(citation_pdf_urls[0]).path if citation_pdf_urls else None
    new_pdf_urls = [pdf_url for pdf_url in pdf_urls if urlparse(pdf_url).path != citation_pdf_path]

    # if len(section_nodes) == 0 and citation_pdf_urls:
    #     print(f'*** {act_url}')

    act_details = ActDetails(
        url=act_url,
        web_act_id=web_act_id,
        web_number=act_web_number,
        chapters=chapters,
        sections=sections,
        pdf_urls=new_pdf_urls,
        citation_pdf_urls=citation_pdf_urls
    )
    json_path = act_dir / f'{act_web_number}.json'
    json_path.write_text(act_details.model_dump_json())
    return act_details


def extract_pdf_links(html_tree):
    """Extract PDF links from the HTML tree.

    Args:
        html_tree: Parsed HTML tree from lxml.etree

    Returns:
        tuple: (citation_pdf_urls, other_pdf_urls)
    """
    # Extract citation PDF URLs from meta tags
    citation_urls = html_tree.xpath('//meta[@name="citation_pdf_url"]/@content')

    # Otherwise, find all PDF links with bitstream in the URL
    pdf_links = html_tree.xpath('//a[contains(@href, "/bitstream/") and contains(@href, ".pdf")]/@href')
    # Make sure URLs are absolute
    pdf_links = [
        url if url.startswith('http') else f'https://www.indiacode.nic.in{url}'
        for url in pdf_links
    ]
    return citation_urls, pdf_links


WebsiteDir = Path("import/website")

def main():
    act_infos_file = Path(sys.argv[1])
    act_infos = json.loads(act_infos_file.read_text())
    num_acts = len(act_infos)
    for idx, act_info in enumerate(act_infos):
        url = act_info['View']
        act_web_number = url.replace('?view_type=browse', '').split('/')[-1]

        print(f'[{idx}/{num_acts}]: ({act_web_number}) {act_info["Short Title"]}')
        print(url)

        state_dir = WebsiteDir / act_infos_file.parent.name

        # Get act details
        act_details = fetch_act(url, act_web_number, state_dir)

        # Download Act PDF
        act_pdf = state_dir / act_web_number / 'act_web_number.pdf'

        # Get section details
        for section_info in act_details.sections:
            section_dir = state_dir / act_web_number / 'sections'
            section_dir.mkdir(exist_ok=True, parents=True)

            # fetch section information
            fetch_section(act_details.web_act_id, section_info, section_dir)

        # Download both citation and act pdfs
        if act_details.citation_pdf_urls:
            citation_pdf_url = act_details.citation_pdf_urls[0]
            citation_pdf = state_dir / act_web_number / 'citation_pdf' / Path(citation_pdf_url).name
            if len(citation_pdf.name) > 128:
                citation_pdf = citation_pdf.parent / f'{act_web_number}.pdf'

            if citation_pdf.exists():
                print(f'\tCitation PDF: {citation_pdf_url}: already exists')
            else:
                print(f'\tCitation PDF: {citation_pdf_url}: fetching...')
                fetch_pdf(citation_pdf_url, citation_pdf)

            # If there are sections and citation_pdf exists, extract last updated date

            date_json_path = citation_pdf.parent / 'last_updated_date.json'
            if act_details.sections and citation_pdf.exists():# and not date_json_path.exists():
                # if str(act_web_number) == '19823':
                #     import pdb
                #     pdb.set_trace()
                date_str, joined_texts   = extract_date_from_citation_pdf(str(citation_pdf))
                # print('\n'.join(joined_texts))
                if date_str:
                    with open(date_json_path, 'w') as f:
                        json.dump({'last_updated_date': date_str}, f)
                    print(f'\tExtracted last updated date: {date_str}')
                else:
                    print(f'#\tNo last updated date found. {citation_pdf_url}.')
                    print('#' + '\n#'.join(joined_texts) + '\n#===========================')

                #import pdb; pdb.set_trace()

        for act_pdf_url in act_details.pdf_urls:
            act_pdf_url = act_pdf_url.replace('nic.in ', 'nic.in')
            act_pdf = state_dir / act_web_number / 'act_pdfs' / Path(act_pdf_url).name
            if len(act_pdf.name) > 128:
                act_pdf = act_pdf.parent / f'{act_web_number}.pdf'
            if act_pdf.exists():
                print(f'\tAct PDF: {act_pdf_url}: already exists')
            else:
                print(f'\tAct PDF: {act_pdf_url}: fetching...')
                fetch_pdf(act_pdf_url, act_pdf)

    close_browser()




if __name__ == '__main__':
    main()
