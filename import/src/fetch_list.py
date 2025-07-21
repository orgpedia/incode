import requests
from lxml import html
import sys
from pathlib import Path
import json
import subprocess

Website = 'https://www.indiacode.nic.in/'

def fetch_page(url):
    response = requests.get(url)
    return response.text


def fetch_page_curl(url):
    # use curl to fetch the page
    response = subprocess.check_output(['curl', url])
    return response.decode('utf-8')

def get_num_acts(html_str):
    tree = html.fromstring(html_str)

    # Extract the text content
    text = tree.xpath('//div[@class="panel-footer text-center"]/text()')

    # Find the line that contains the number
    for line in text:
        line = line.strip()
        if 'of' in line:
            # Extract the number after 'of'
            parts = line.split('of')
            if len(parts) > 1:
                number = parts[1].strip()
                return int(number)
    return None

TableFields = ['Enactment Date', 'Act Number', 'Short Title', 'View']
def extract_row_infos(html_str):
    tree = html.fromstring(html_str)
    table = tree.xpath('//table')[0]
    rows = table.xpath('//tr')
    row_infos = []
    for row in rows:
        cells = row.xpath('.//td')
        row_info = {}
        for (idx, field) in enumerate(TableFields):
            if field == 'View':
                row_info[field] = Website + cells[idx].xpath('.//a/@href')[0]
            else:
                row_info[field] = cells[idx].text_content().strip()
        row_infos.append(row_info)
    return row_infos

def save_list(name, href_stub, website_dir: Path):
    name_dir =  website_dir / name.replace(' ', '_')
    if (name_dir / 'act_infos.json').exists():
        print(f'{name}: already exists')
        act_infos = json.loads((name_dir / 'act_infos.json').read_text())
        return len(act_infos)

    first_url = Website + href_stub + '/browse?type=dateissued&sort_by=1&order=ASC&rpp=100'
    html_str = fetch_page_curl(first_url)

    name_dir.mkdir(exist_ok=True, parents=True)
    html_path = name_dir / f'{name}-1.html'
    html_path.write_text(html_str)

    num_acts = get_num_acts(html_str)
    # calculate number of pages assuming 100 acts per page
    num_pages = (num_acts + 99) // 100

    act_infos = []
    act_infos.extend(extract_row_infos(html_str))

    for page in range(2, num_pages + 1):
        url = Website + href_stub + '/browse?type=dateissued&sort_by=1&order=ASC&rpp=100&etal=-1&null=&offset=' + str((page - 1) * 100)

        html_path = name_dir / f'{name}-{page}.html'
        html_path.write_text(fetch_page_curl(url))
        act_infos.extend(extract_row_infos(html_path.read_text()))
    (name_dir / 'act_infos.json').write_text(json.dumps(act_infos))
    return len(act_infos)

WebsiteDir = Path('import/website')
if __name__ == '__main__':
    json_file = Path(sys.argv[1])
    name_list = json.loads(json_file.read_text())
    for name_dict in name_list:
        name = name_dict['name']
        href_stub = name_dict['href']
        num_acts = save_list(name, href_stub, WebsiteDir)
        print(f'{name}: {num_acts}')


