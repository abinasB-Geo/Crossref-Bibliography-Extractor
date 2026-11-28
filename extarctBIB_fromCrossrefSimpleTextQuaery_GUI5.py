
import re
import csv
import sys
import time
import queue
import threading
import requests

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from pathlib import Path
from urllib.parse import quote, unquote


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "Crossref Bibliography Extractor"

SEMANTIC_SCHOLAR_API_KEY = ""  # Optional: enter API key if available

CROSSREF_MAILTO = ""  # Optional: enter your email address


# ============================================================
# DOI EXTRACTION
# ============================================================

def extract_dois(text):
    """
    Extract complete DOI identifiers from bibliography text.

    Supports:
    - DOI URLs
    - Markdown DOI hyperlinks
    - Escaped URLs (https\\://)
    - Parentheses and special characters
    - Percent-encoded DOI characters
    - DOI URLs on separate lines
    """

    dois = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        # Normalize escaped characters
        line = line.replace(r'\:', ':')
        line = line.replace(r'\(', '(')
        line = line.replace(r'\)', ')')

        # Find DOI URLs
        matches = re.findall(
            r'https?://(?:dx\.)?doi\.org/[^\s\]]+',
            line,
            flags=re.IGNORECASE
        )

        # Find bare DOI identifiers if no URL exists
        if not matches:
            matches = re.findall(
                r'10\.\d{4,9}/\S+',
                line,
                flags=re.IGNORECASE
            )

        for doi in matches:

            # Remove DOI URL prefix
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

            # Remove trailing Markdown delimiters
            doi = doi.rstrip('\\`*_')

            # Remove unmatched closing parentheses
            while doi.endswith(')') and doi.count(')') > doi.count('('):
                doi = doi[:-1]

            doi = doi.strip()

            if doi and doi not in dois:
                dois.append(doi)

    return dois


# ============================================================
# BIBTEX UTILITIES
# ============================================================

def bibtex_escape(value):

    if value is None:
        return ""

    value = str(value)

    replacements = {
        "&": r"\&",
        "%": r"\%",
        "_": r"\_",
        "#": r"\#"
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return value


def make_citation_key(metadata, doi):

    authors = metadata.get("authors", [])

    if authors:
        first_author = authors[0].get("family", "Unknown")
    else:
        first_author = "Unknown"

    first_author = re.sub(r'[^a-zA-Z0-9]', '', first_author)

    year = str(metadata.get("year", "nd"))

    title = metadata.get("title", "Untitled")

    first_word = re.sub(
        r'[^a-zA-Z0-9]',
        '',
        title.split()[0] if title.split() else "Untitled"
    )

    return f"{first_author}{year}{first_word}"


def create_bibtex(metadata, doi):

    entry_type = metadata.get("entry_type", "article")

    key = make_citation_key(metadata, doi)

    fields = {
        "author": metadata.get("author"),
        "title": metadata.get("title"),
        "journal": metadata.get("journal"),
        "booktitle": metadata.get("booktitle"),
        "year": metadata.get("year"),
        "volume": metadata.get("volume"),
        "number": metadata.get("number"),
        "pages": metadata.get("pages"),
        "publisher": metadata.get("publisher"),
        "doi": doi,
        "url": f"https://doi.org/{doi}"
    }

    lines = [f"@{entry_type}{{{key},"]

    for field, value in fields.items():

        if value is None or value == "":
            continue

        value = bibtex_escape(value)

        lines.append(f"    {field} = {{{value}}},")

    lines.append("}")

    return "\n".join(lines)


# ============================================================
# METHOD 1: DIRECT DOI TO BIBTEX CONVERSION
# ============================================================

def get_bibtex_direct(doi):

    print(f"[DOI] Trying direct BibTeX conversion: {doi}")

    url = "https://doi.org/" + quote(
        doi,
        safe="/()!$&'*,;=:@-._~"
    )

    headers = {
        "Accept": "application/x-bibtex",
        "User-Agent": "CrossrefBibliographyExtractor/1.0"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        bibtex = response.text.strip()

        if bibtex.startswith("@") and "{" in bibtex:

            print("[SUCCESS] Direct BibTeX conversion successful.")

            return bibtex

        print("[WARNING] Direct conversion returned invalid BibTeX.")

        return None

    except requests.RequestException as error:

        print(f"[WARNING] Direct DOI conversion failed: {error}")

        return None


# ============================================================
# METHOD 2: CROSSREF API
# ============================================================

def get_crossref_metadata(doi):

    print(f"[CROSSREF] Searching: {doi}")

    url = "https://api.crossref.org/works/" + quote(
        doi,
        safe=""
    )

    headers = {
        "User-Agent": "CrossrefBibliographyExtractor/1.0"
    }

    params = {}

    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()["message"]

        title = (
            data.get("title", [""])[0]
            if data.get("title")
            else ""
        )

        authors = []

        for author in data.get("author", []):

            authors.append({
                "given": author.get("given", ""),
                "family": author.get("family", "")
            })

        # Publication year
        year = None

        for date_field in [
            "published-print",
            "published-online",
            "issued",
            "created"
        ]:

            date_parts = (
                data.get(date_field, {})
                .get("date-parts", [])
            )

            if date_parts and date_parts[0]:
                year = date_parts[0][0]
                break

        journal = (
            data.get("container-title", [""])[0]
            if data.get("container-title")
            else ""
        )

        pages = data.get("page", "")

        if not pages:
            pages = data.get("article-number", "")

        entry_type = data.get("type", "journal-article")

        if entry_type == "proceedings-article":
            bib_type = "inproceedings"
        elif entry_type == "book":
            bib_type = "book"
        elif entry_type == "book-chapter":
            bib_type = "incollection"
        elif entry_type == "report":
            bib_type = "techreport"
        else:
            bib_type = "article"

        metadata = {

            "entry_type": bib_type,

            "title": title,

            "authors": authors,

            "author": " and ".join(
                f"{a['family']}, {a['given']}".strip(", ")
                for a in authors
            ),

            "journal": journal,

            "booktitle": (
                journal if bib_type == "inproceedings" else None
            ),

            "year": year,

            "volume": data.get("volume"),

            "number": data.get("issue"),

            "pages": pages,

            "publisher": data.get("publisher")
        }

        if not metadata["title"]:
            print("[WARNING] Crossref returned no title.")
            return None

        print("[SUCCESS] Crossref metadata retrieved.")

        return metadata

    except (requests.RequestException, ValueError, KeyError, IndexError) as error:

        print(f"[WARNING] Crossref lookup failed: {error}")

        return None


# ============================================================
# METHOD 3: SEMANTIC SCHOLAR API
# ============================================================

def get_semantic_scholar_metadata(doi):

    print(f"[SEMANTIC SCHOLAR] Searching: {doi}")

    url = (
        "https://api.semanticscholar.org/graph/v1/paper/DOI:"
        + quote(doi, safe="")
    )

    headers = {}

    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    params = {
        "fields": "title,authors,year,venue,journal,publicationVenue,externalIds,url"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        authors = []

        for author in data.get("authors", []):

            name = author.get("name", "").strip()

            if name:

                parts = name.rsplit(" ", 1)

                if len(parts) == 2:
                    given, family = parts
                else:
                    given, family = "", name

                authors.append({
                    "given": given,
                    "family": family
                })

        journal_data = data.get("journal") or {}
        venue_data = data.get("publicationVenue") or {}

        journal = (
            journal_data.get("name")
            or data.get("venue")
            or venue_data.get("name")
            or ""
        )

        metadata = {

            "entry_type": "article",

            "title": data.get("title", ""),

            "authors": authors,

            "author": " and ".join(
                f"{a['family']}, {a['given']}".strip(", ")
                for a in authors
            ),

            "journal": journal,

            "year": data.get("year"),

            "volume": journal_data.get("volume"),

            "number": None,

            "pages": journal_data.get("pages"),

            "publisher": None
        }

        if not metadata["title"]:
            print("[WARNING] Semantic Scholar returned no title.")
            return None

        print("[SUCCESS] Semantic Scholar metadata retrieved.")

        return metadata

    except (requests.RequestException, ValueError, KeyError) as error:

        print(f"[WARNING] Semantic Scholar lookup failed: {error}")

        return None


# ============================================================
# COMPLETE DOI RETRIEVAL WORKFLOW
# ============================================================

def retrieve_bibtex(doi):

    # METHOD 1: Direct DOI conversion
    bibtex = get_bibtex_direct(doi)

    if bibtex:
        return bibtex, "Direct DOI Conversion"

    # METHOD 2: Crossref
    metadata = get_crossref_metadata(doi)

    if metadata:

        bibtex = create_bibtex(metadata, doi)

        return bibtex, "Crossref API"

    # METHOD 3: Semantic Scholar
    metadata = get_semantic_scholar_metadata(doi)

    if metadata:

        bibtex = create_bibtex(metadata, doi)

        return bibtex, "Semantic Scholar API"

    print(f"[FAILED] All retrieval methods failed: {doi}")

    return None, "Failed"


# ============================================================
# OUTPUT FILENAME
# ============================================================

def safe_filename(doi):

    name = re.sub(
        r'[^a-zA-Z0-9._-]',
        '_',
        doi
    )

    return name[:150]


# ============================================================
# PROCESS BIBLIOGRAPHY
# ============================================================

def process_bibliography(input_file, output_folder):

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\n" + "=" * 65)
    print(" CROSSREF BIBLIOGRAPHY EXTRACTOR")
    print("=" * 65)

    print(f"\nInput file: {input_file}")

    print(f"Output folder: {output_folder}")

    # Read input file
    try:

        text = input_file.read_text(
            encoding="utf-8-sig",
            errors="replace"
        )

    except Exception as error:

        print(f"[ERROR] Cannot read input file: {error}")

        return False

    # Extract DOIs
    dois = extract_dois(text)

    total = len(dois)

    print(f"\n[INFO] Total unique DOIs detected: {total}")

    if total == 0:

        print("[WARNING] No DOIs found in the input file.")

        return False

    combined_bibtex = []

    report = []

    successful = 0
    failed = 0

    for index, doi in enumerate(dois, start=1):

        print("\n" + "-" * 65)

        print(f"[PROCESSING] DOI {index} of {total}")

        print(f"DOI: {doi}")

        try:

            bibtex, source = retrieve_bibtex(doi)

            if bibtex:

                filename = safe_filename(doi) + ".bib"

                output_file = output_folder / filename

                output_file.write_text(
                    bibtex + "\n",
                    encoding="utf-8"
                )

                combined_bibtex.append(bibtex)

                successful += 1

                print(f"[SAVED] {filename}")

                report.append([
                    doi,
                    "Success",
                    source,
                    filename
                ])

            else:

                failed += 1

                report.append([
                    doi,
                    "Failed",
                    source,
                    ""
                ])

        except Exception as error:

            failed += 1

            print(f"[ERROR] Processing DOI failed: {error}")

            report.append([
                doi,
                "Failed",
                str(error),
                ""
            ])

        # Small delay between API requests
        time.sleep(0.3)

    # Save combined bibliography
    combined_file = output_folder / "Combined_Bibliography.bib"

    combined_file.write_text(
        "\n\n".join(combined_bibtex),
        encoding="utf-8"
    )

    print("\n[SAVED] Combined_Bibliography.bib")

    # Save CSV report
    report_file = output_folder / "Bibliography_Report.csv"

    with open(
        report_file,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as csvfile:

        writer = csv.writer(csvfile)

        writer.writerow([
            "DOI",
            "Status",
            "Retrieval Method",
            "BibTeX File"
        ])

        writer.writerows(report)

    print("[SAVED] Bibliography_Report.csv")

    # Final summary
    print("\n" + "=" * 65)
    print(" EXTRACTION SUMMARY")
    print("=" * 65)

    print(f"Total unique DOIs : {total}")
    print(f"Successful        : {successful}")
    print(f"Failed            : {failed}")

    print(f"\nOutput folder:\n{output_folder}")

    print("\n[COMPLETE] Bibliography extraction finished.")

    return True


# ============================================================
# TKINTER PRINT LOGGER
# ============================================================

class PrintLogger:

    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, message):

        if message:
            self.log_queue.put(message)

    def flush(self):
        pass


# ============================================================
# TKINTER APPLICATION
# ============================================================

def main():

    # Create initial hidden window
    root = tk.Tk()

    root.withdraw()

    root.attributes("-topmost", True)

    # Select input bibliography
    input_file = filedialog.askopenfilename(

        parent=root,

        title="Select Crossref Simple Text Query Output",

        filetypes=[
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
    )

    if not input_file:

        root.destroy()

        return

    input_file = Path(input_file)

    # Automatically create output folder
    output_folder = (
        input_file.parent
        / input_file.stem
        / "Crossref_Extracted"
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # Configure application window
    root.deiconify()

    root.title(APP_NAME)

    root.geometry("850x550")

    root.minsize(600, 400)

    root.attributes("-topmost", True)

    # Heading
    heading = ttk.Label(

        root,

        text=APP_NAME,

        font=("Arial", 16, "bold")
    )

    heading.pack(pady=12)

    # Selected file information
    file_label = ttk.Label(

        root,

        text=f"Input: {input_file.name}",

        font=("Arial", 9)
    )

    file_label.pack(pady=2)

    # Progress bar
    progress = ttk.Progressbar(

        root,

        mode="indeterminate"
    )

    progress.pack(
        fill="x",
        padx=15,
        pady=10
    )

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

        padx=12,

        pady=8
    )

    # Queue for thread-safe GUI logging
    log_queue = queue.Queue()

    logger = PrintLogger(log_queue)

    # Redirect print output
    sys.stdout = logger
    sys.stderr = logger

    # Status label
    status_label = ttk.Label(

        root,

        text="Starting application..."
    )

    status_label.pack(pady=8)

    # Completion state
    finished = threading.Event()

    result = {"success": False}

    # Background processing
    def worker():

        try:

            result["success"] = process_bibliography(
                input_file,
                output_folder
            )

        except Exception as error:

            print(f"\n[FATAL ERROR] {error}")

        finally:

            finished.set()

    # Start processing in background thread
    threading.Thread(

        target=worker,

        daemon=True

    ).start()

    progress.start(10)

    status_label.config(
        text="Processing bibliography..."
    )

    # Update GUI from queue
    def update_log():

        while not log_queue.empty():

            message = log_queue.get()

            log_text.insert(tk.END, message)

            log_text.see(tk.END)

        if finished.is_set():

            # Display remaining messages
            while not log_queue.empty():

                log_text.insert(
                    tk.END,
                    log_queue.get()
                )

            progress.stop()

            if result["success"]:

                status_label.config(
                    text="Extraction completed successfully!"
                )

                log_text.insert(
                    tk.END,
                    "\n\nAPPLICATION FINISHED SUCCESSFULLY."
                )

            else:

                status_label.config(
                    text="Processing finished. Check the log."
                )

            log_text.see(tk.END)

            return

        root.after(100, update_log)

    root.after(100, update_log)

    # Keep application window open
    root.mainloop()


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    main()
