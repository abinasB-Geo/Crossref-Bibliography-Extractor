
import re
import csv
import time
import requests
import sys

from pathlib import Path
from collections import Counter
from urllib.parse import quote

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

class PrintLogger:
    """Redirect print output to a Tkinter log window."""

    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)

        # Refresh GUI immediately
        self.root.update_idletasks()
        self.root.update()

    def flush(self):
        pass


def select_input_file():
    """Open a file browser to select the bibliography text file."""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_path = filedialog.askopenfilename(
        title="Select Bibliography Text File",
        filetypes=[
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
    )

    root.destroy()

    if not file_path:
        return None

    return Path(file_path)


def create_output_folder(input_file):
    """Create output folder beside the selected input file."""

    parent_folder = input_file.parent

    # Remove the file extension from the input filename
    folder_name = input_file.stem

    output_folder = (
        parent_folder /
        folder_name /
        "Crossref_Extracted"
    )

    output_folder.mkdir(parents=True, exist_ok=True)

    return output_folder


# ============================================================
# USER SETTINGS
# ============================================================

# Select bibliography file using Windows File Explorer
INPUT_FILE = select_input_file()

if INPUT_FILE is None:
    print("No input file selected. Program terminated.")
    raise SystemExit

# Automatically generate output folder
OUTPUT_FOLDER = create_output_folder(INPUT_FILE)

print("\nSelected input file:")
print(INPUT_FILE)

print("\nOutput folder:")
print(OUTPUT_FOLDER)

# ================= GUI LOG WINDOW =================

root = tk.Tk()
root.title("Crossref Bibliography Extractor")
root.geometry("750x450")
root.minsize(550, 300)

# Application heading
heading = tk.Label(
    root,
    text="Crossref Bibliography Extractor",
    font=("Arial", 15, "bold"),
    pady=10
)
heading.pack()

# Log window
log_text = ScrolledText(
    root,
    wrap=tk.WORD,
    font=("Consolas", 10),
    bg="#1e1e1e",
    fg="#00ff88",
    insertbackground="white"
)

log_text.pack(
    fill=tk.BOTH,
    expand=True,
    padx=10,
    pady=10
)

# Redirect print() output to GUI
logger = PrintLogger(log_text, root)

sys.stdout = logger
sys.stderr = logger

print("=" * 60)
print(" CROSSREF BIBLIOGRAPHY EXTRACTOR")
print("=" * 60)
print("Application started successfully.")
print(f"Input file: {INPUT_FILE}")
print(f"Output folder: {OUTPUT_FOLDER}")
print("=" * 60)

# ===================================================


EMAIL = "your_email@example.com"

# Optional: Semantic Scholar API key.
# Leave empty if you do not have one.
SEMANTIC_SCHOLAR_API_KEY = ""

DELAY = 1.0

# ============================================================
# OUTPUT FOLDERS
# ============================================================

INDIVIDUAL_FOLDER = OUTPUT_FOLDER / "Individual_BIB"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
INDIVIDUAL_FOLDER.mkdir(parents=True, exist_ok=True)

COMBINED_FILE = OUTPUT_FOLDER / "Combined_Bibliography.bib"
REPORT_FILE = OUTPUT_FOLDER / "Bibliography_Report.csv"


# ============================================================
# API SETTINGS
# ============================================================

CROSSREF_URL = "https://api.crossref.org/works"

SEMANTIC_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/"
)

session = requests.Session()

session.headers.update({
    "User-Agent": f"BibExtractor/1.0 (mailto:{EMAIL})"
})

if SEMANTIC_SCHOLAR_API_KEY:
    session.headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY


# ============================================================
# 1. READ BIBLIOGRAPHY
# ============================================================

def read_bibliography():

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8-sig"
    ) as f:

        return [
            line.strip()
            for line in f
            if line.strip()
        ]


# ============================================================
# 2. EXTRACT DOI FROM TEXT AND MARKDOWN LINKS
# ============================================================

import re
from urllib.parse import unquote

def extract_dois(text):
    """
    Extract complete DOI identifiers from bibliography text.

    DOI is considered complete up to the end of its line.
    Supports Markdown links, plain DOI URLs, escaped URLs,
    and special DOI characters.
    """

    dois = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        # Convert escaped URL characters
        line = line.replace(r'\:', ':')
        line = line.replace(r'\(', '(')
        line = line.replace(r'\)', ')')

        # Find DOI URLs in the line
        matches = re.findall(
            r'https?://(?:dx\.)?doi\.org/\S+',
            line,
            flags=re.IGNORECASE
        )

        # Find bare DOI identifiers if no DOI URL exists
        if not matches:
            matches = re.findall(
                r'10\.\d{4,9}/\S+',
                line,
                flags=re.IGNORECASE
            )

        for doi in matches:

            # Remove URL prefix
            doi = re.sub(
                r'^https?://(?:dx\.)?doi\.org/',
                '',
                doi,
                flags=re.IGNORECASE
            )

            # Decode percent-encoded characters
            doi = unquote(doi)

            # Remove Markdown closing link syntax
            doi = re.sub(r'\]\(.*$', '', doi)

            # Remove only trailing Markdown delimiters
            doi = doi.rstrip('\\`*_')

            doi = doi.strip()

            if doi and doi not in dois:
                dois.append(doi)

    return dois



# ============================================================
# 3. CROSSREF API
# ============================================================

def get_crossref(doi):

    encoded_doi = quote(doi, safe="")

    url = f"{CROSSREF_URL}/{encoded_doi}"

    try:

        response = session.get(
            url,
            params={"mailto": EMAIL},
            timeout=30
        )

        response.raise_for_status()

        item = response.json()["message"]

        if not item.get("title"):
            return None

        return item

    except requests.RequestException as error:

        print("Crossref failed:", error)

        return None

    except (ValueError, KeyError):

        return None


# ============================================================
# 4. SEMANTIC SCHOLAR FALLBACK
# ============================================================

def get_semantic_scholar(doi):

    paper_id = "DOI:" + doi

    url = (
        SEMANTIC_URL +
        quote(paper_id, safe=":")
    )

    params = {
        "fields": (
            "title,authors,year,venue,publicationVenue,"
            "journal,volume,issue,pages,externalIds,"
            "publicationTypes,abstract,url"
        )
    }

    for attempt in range(3):

        try:

            response = session.get(
                url,
                params=params,
                timeout=30
            )

            if response.status_code == 404:
                return None

            if response.status_code == 429:

                print("Semantic Scholar rate limited. Waiting...")

                time.sleep(5 * (attempt + 1))
                continue

            response.raise_for_status()

            item = response.json()

            if not item.get("title"):
                return None

            return item

        except requests.RequestException as error:

            print("Semantic Scholar error:", error)

            time.sleep(2 * (attempt + 1))

    return None


# ============================================================
# 5. COMMON METADATA EXTRACTION
# ============================================================

def get_metadata_value(item, key):

    value = item.get(key)

    if isinstance(value, list):

        return value[0] if value else ""

    if value is None:
        return ""

    return str(value)


def metadata_to_common(item, source):

    if source == "Crossref":

        authors = []

        for author in item.get("author", []):

            family = author.get("family", "")
            given = author.get("given", "")

            if family and given:
                authors.append(f"{family}, {given}")

            elif family:
                authors.append(family)

            elif author.get("name"):
                authors.append(author["name"])

        journal = get_metadata_value(
            item, "container-title"
        )

        year = ""

        for field in [
            "published-print",
            "published-online",
            "published",
            "issued"
        ]:

            parts = item.get(
                field, {}
            ).get("date-parts", [])

            if parts and parts[0]:
                year = str(parts[0][0])
                break

        return {
            "type": item.get("type", ""),
            "title": get_metadata_value(item, "title"),
            "author": " and ".join(authors),
            "year": year,
            "journal": journal,
            "publisher": item.get("publisher", ""),
            "volume": item.get("volume", ""),
            "number": item.get("issue", ""),
            "pages": item.get("page", ""),
            "doi": item.get("DOI", ""),
            "url": item.get("URL", ""),
            "abstract": item.get("abstract", ""),
            "isbn": get_metadata_value(item, "ISBN"),
            "issn": get_metadata_value(item, "ISSN")
        }

    else:

        authors = []

        for author in item.get("authors", []):

            name = author.get("name", "")

            if name:
                authors.append(name)

        journal_info = item.get("journal") or {}
        venue_info = item.get("publicationVenue") or {}

        journal = (
            journal_info.get("name")
            or venue_info.get("name")
            or item.get("venue", "")
        )

        return {
            "type": "journal-article",
            "title": item.get("title", ""),
            "author": " and ".join(authors),
            "year": str(item.get("year") or ""),
            "journal": journal,
            "publisher": "",
            "volume": journal_info.get("volume", ""),
            "number": journal_info.get("pages", ""),
            "pages": journal_info.get("pages", "")
                     or item.get("pages", ""),
            "doi": item.get("externalIds", {}).get(
                "DOI", ""
            ),
            "url": item.get("url", ""),
            "abstract": item.get("abstract", ""),
            "isbn": "",
            "issn": ""
        }


# ============================================================
# 6. CREATE CITATION KEY
# ============================================================

def create_key(meta):

    author = meta["author"].split(" and ")[0]

    author = re.sub(
        r"[^A-Za-z0-9]",
        "",
        author.split(",")[0]
    )

    year = meta["year"] or "nd"

    title_words = re.findall(
        r"[A-Za-z0-9]+",
        meta["title"]
    )

    first_word = (
        title_words[0] if title_words else "Untitled"
    )

    return f"{author}{year}{first_word}"


# ============================================================
# 7. BIBTEX ENTRY TYPE
# ============================================================

def get_bib_type(meta):

    mapping = {
        "journal-article": "article",
        "book": "book",
        "monograph": "book",
        "book-chapter": "incollection",
        "book-section": "incollection",
        "proceedings-article": "inproceedings",
        "dissertation": "phdthesis",
        "report": "techreport"
    }

    return mapping.get(meta["type"], "misc")


# ============================================================
# 8. BIBTEX ESCAPING
# ============================================================

def bibtex_escape(value):

    value = str(value)

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_"
    }

    for old, new in replacements.items():

        value = value.replace(old, new)

    return value


# ============================================================
# 9. CREATE BIBTEX
# ============================================================

def create_bibtex(meta, key):

    entry_type = get_bib_type(meta)

    fields = {
        "author": meta["author"],
        "title": meta["title"],
        "year": meta["year"],
        "journal": meta["journal"],
        "publisher": meta["publisher"],
        "volume": meta["volume"],
        "number": meta["number"],
        "pages": meta["pages"],
        "doi": meta["doi"],
        "url": meta["url"],
        "abstract": meta["abstract"],
        "isbn": meta["isbn"],
        "issn": meta["issn"]
    }

    fields = {
        k: v for k, v in fields.items()
        if v
    }

    # Use booktitle for conference papers
    if entry_type == "inproceedings" and "journal" in fields:

        fields["booktitle"] = fields.pop("journal")

    bib = f"@{entry_type}{{{key},\n"

    for field, value in fields.items():

        bib += (
            f"  {field} = "
            f"{{{bibtex_escape(value)}}},\n"
        )

    bib += "}\n\n"

    return bib


# ============================================================
# 10. MAIN PROGRAM
# ============================================================

def main():

    if not INPUT_FILE.exists():

        print("ERROR: Input file not found!")

        print(INPUT_FILE)

        return

    lines = read_bibliography()

    # Extract DOI and keep original line number
    records = []

    for line_number, line in enumerate(lines, start=1):

        dois = extract_dois(line)

        for doi in dois:

            records.append({
                "line": line_number,
                "reference": line,
                "doi": doi
            })

    # Deduplicate repeated DOI records
    unique_records = []
    seen_dois = set()

    for record in records:

        doi_key = record["doi"].lower()

        if doi_key not in seen_dois:

            seen_dois.add(doi_key)
            unique_records.append(record)

    print("\n======================================")
    print(" DOI BIBTEX EXTRACTOR")
    print("======================================")

    print("Bibliography lines:", len(lines))
    print("DOI occurrences:", len(records))
    print("Unique DOIs:", len(unique_records))

    compiled = []

    report = []

    used_keys = set()

    crossref_count = 0
    semantic_count = 0
    failed_count = 0

    # ========================================================
    # PROCESS EVERY DOI
    # ========================================================

    for index, record in enumerate(
        unique_records, start=1
    ):

        doi = record["doi"]

        print(
            f"\n[{index}/{len(unique_records)}] {doi}"
        )

        source = ""

        # Primary: Crossref
        item = get_crossref(doi)

        if item:

            source = "Crossref"

            crossref_count += 1

        else:

            print("Trying Semantic Scholar...")

            # Fallback: Semantic Scholar
            item = get_semantic_scholar(doi)

            if item:

                source = "Semantic Scholar"

                semantic_count += 1

        # Neither API found the paper
        if not item:

            print("FAILED: No metadata found")

            report.append([
                record["line"],
                doi,
                "",
                "",
                "FAILED"
            ])

            failed_count += 1

            time.sleep(DELAY)

            continue

        # Convert to common metadata
        meta = metadata_to_common(item, source)

        # Citation key
        key = create_key(meta)

        original_key = key

        counter = 2

        while key.lower() in used_keys:

            key = f"{original_key}_{counter}"

            counter += 1

        used_keys.add(key.lower())

        # Create BibTeX
        bibtex = create_bibtex(meta, key)

        # Save individual BibTeX
        filename = f"{index:04d}_{key}.bib"

        individual_path = (
            INDIVIDUAL_FOLDER / filename
        )

        with open(
            individual_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(bibtex)

        compiled.append(bibtex)

        print("Title:", meta["title"])
        print("Source:", source)
        print("Saved:", filename)

        report.append([
            record["line"],
            doi,
            meta["title"],
            source,
            "SUCCESS"
        ])

        time.sleep(DELAY)

    # ========================================================
    # SAVE COMPILED BIBLIOGRAPHY
    # ========================================================

    with open(
        COMBINED_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write("\n".join(compiled))

    # ========================================================
    # SAVE REPORT
    # ========================================================

    with open(
        REPORT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "Original Line",
            "DOI",
            "Title",
            "Metadata Source",
            "Status"
        ])

        writer.writerows(report)

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n======================================")
    print("             COMPLETED")
    print("======================================")

    print("Unique DOIs:", len(unique_records))

    print("Crossref success:", crossref_count)

    print("Semantic Scholar success:", semantic_count)

    print("Failed:", failed_count)

    print("\nOutput folder:")
    print(OUTPUT_FOLDER)

    print("\nCombined BibTeX:")
    print(COMBINED_FILE)

    print("\nReport:")
    print(REPORT_FILE)

    print("\n======================================")


if __name__ == "__main__":
    main()
    
print("\n" + "=" * 60)
print("ALL TASKS COMPLETED SUCCESSFULLY!")
print("=" * 60)

print(f"\nOutput location:\n{OUTPUT_FOLDER}")

print("\nYou can now close this window.")

# Keep GUI open until user closes it
root.mainloop()
