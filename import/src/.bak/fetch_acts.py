import json
from pydantic import BaseModel
from typing import List, Tuple, Optional
from pathlib import Path
import sys
import time
import subprocess


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

def fetch_page_curl(url):
    # use curl to fetch the page
    time.sleep(2)
    response = subprocess.check_output(['curl', url])
    return response.decode('utf-8')



def fetch_act(url, act_web_number, website_dir: Path):
    # Load HTML file
    act_dir = website_dir / act_web_number
    act_dir.mkdir(exist_ok=True, parents=True)

    html_path = act_dir / f'{act_web_number}.html'
    json_path = act_dir / f'{act_web_number}.json'

    if json_path.exists():
        print(f'{act_web_number}: already exists')
        return json.loads(json_path.read_text())

    if html_path.exists():
        html_str = html_path.read_text()
    else:
        html_str = fetch_page_curl(url)
        html_path.write_text(html_str)

    from lxml import etree
    parser = etree.HTMLParser()
    tree = etree.fromstring(html_str, parser)

    # --- Extract Act Details ---
    # act_id = tree.xpath('//div[@id="tb2"]//td[contains(text(),"Act ID")]/following-sibling::td[1]/text()')
    # act_web_number = act_id[0].strip() if act_id else ""

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
    sections, web_act_id = [], ''
    section_nodes = tree.xpath('//table[@id="myTableActSection"]//a[@class="title"]')
    for idx, sec in enumerate(section_nodes):

        sec_id = sec.attrib.get("id", "")
        web_act_id = sec_id.split('#')[0]
        web_number = sec_id.split('#')[1]
        href = sec.attrib.get("href", "")
        url = href if href.startswith("http") else ("https://www.indiacode.nic.in" + href)
        number = sec.find('span').text.strip()
        title = sec.find('span').tail.strip()
        span_class = sec.xpath('./span')[0].get('class', '')
        has_notification = 'label-default' in span_class
        sections.append(SectionInfo(web_number=web_number, number=number, title=title, url=url, has_notification=has_notification))

    act_details = ActDetails(url=url, web_act_id=web_act_id, web_number=act_web_number, chapters=chapters, sections=sections)
    json_path = act_dir / f'{act_web_number}.json'
    json_path.write_text(act_details.model_dump_json())
    return act_details



WebsiteDir = Path("import/website")

def main():
    act_infos_file = Path(sys.argv[1])
    act_infos = json.loads(act_infos_file.read_text())
    num_acts = len(act_infos)
    for idx, act_info in enumerate(act_infos):
        url = act_info['View']
        print(f'[{idx}/{num_acts}]: ', act_info['Short Title'])
        print(url)
        act_web_number = url.replace('?view_type=browse', '').split('/')[-1]
        state_dir = WebsiteDir / act_infos_file.parent.name
        fetch_act(url, act_web_number, state_dir)


if __name__ == '__main__':
    main()
