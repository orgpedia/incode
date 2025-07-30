import sys
import json
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_readme.py <State>")
        sys.exit(1)
    state = sys.argv[1]
    state_dir = Path("import/website") / state
    act_infos_path = state_dir / "act_infos.json"
    if not act_infos_path.exists():
        print(f"Could not find {act_infos_path}")
        sys.exit(1)
    act_infos = json.loads(act_infos_path.read_text())

    # Reverse order
    act_infos = list(reversed(act_infos))

    # Prepare Markdown table header
    md = [f"# {state}\n",
        "| Enactment Date | Act Number | Short Title | # Sections | Last Updated Date | Citation PDFs | Other PDFs |",
        "|---|---|---|---|---|---|---|"
    ]
    for act in act_infos:
        act_num = act.get("Act Number", "")
        short_title = act.get("Short Title", "")
        enactment_date = act.get("Enactment Date", "")
        act_web_number = act["View"].replace('?view_type=browse', '').split('/')[-1]
        act_dir = state_dir / act_web_number
        act_json_path = act_dir / f"{act_web_number}.json"
        num_sections = "A/P"
        last_updated_date = ""
        citation_link = ""
        other_pdfs_count = 0
        if act_json_path.exists():
            act_json = json.loads(act_json_path.read_text())
            # # of Sections
            sections = act_json.get("sections", [])
            if len(sections) > 0:
                num_sections = str(len(sections))
            # Citation PDFs (show only [1] if any)
            citation_pdfs = act_json.get("citation_pdf_urls", [])
            if citation_pdfs:
                citation_link = f"[1]({citation_pdfs[0]})"
            # Other PDFs (show only count, not links)
            pdfs = act_json.get("pdf_urls", [])
            other_pdfs_count = len(pdfs)
            # Last updated date
            last_updated_path = act_dir / "citation_pdf" / "last_updated_date.json"
            if last_updated_path.exists():
                try:
                    last_updated_date = json.loads(last_updated_path.read_text()).get("last_updated_date", "")
                except Exception:
                    last_updated_date = ""
        md.append(f"| {enactment_date} | {act_num} | {short_title} | {num_sections} | {last_updated_date} | {citation_link} | {other_pdfs_count} |")
    md.append("\nA/P is 'Awaiting Processing'")
    readme_path = Path("README.md")
    readme_content = "\n".join(md)
    readme_path.write_text(readme_content)
    print(f"README.md generated at {readme_path}")

if __name__ == "__main__":
    main()
