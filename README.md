## Crossref Bibliography Extractor

A Python-based tool that automatically extracts DOI links from bibliography text copied directly from the **Crossref Simple Text Query** output. It retrieves publication metadata using the Crossref API, with **Semantic Scholar API** as a fallback when Crossref lookup fails, and generates individual BibTeX (`.bib`) files for each reference along with a consolidated `Combined_Bibliography.bib` file.

### Features
- Tkinter file browser for selecting the input `.txt` file.
- Automatically creates the output folder alongside the input file.
- Extracts DOI links from Crossref Simple Text Query text.
- Retrieves bibliographic metadata from Crossref, with Semantic Scholar as a fallback.
- Generates individual BibTeX files and a combined bibliography.
- Produces a CSV report of the extraction results.

**Input:** Plain-text output copied from Crossref Simple Text Query and saved as a `.txt` file.

**Output:** Individual `.bib` files, a combined BibTeX bibliography, and a CSV report.


### Standalone Windows Executable (.exe)

A standalone Windows executable is now available for users who prefer running the application without installing Python or configuring dependencies.

- **No Python installation required:** Runs independently on Windows.
- **Easy to use:** Simply double-click the `.exe` file to launch the application.
- **Graphical file selection:** Select your bibliography `.txt` file using the built-in file browser.
- **Automatic output organization:** Creates the output directory alongside the input file.
- **Online metadata retrieval:** Uses Crossref API with Semantic Scholar as a fallback.

**Usage:** Download `Crossref_Bibliography_Extractor.exe` from the repository, run it, and select your Crossref Simple Text Query output file.

**Note:** An active internet connection is required for retrieving publication metadata.
