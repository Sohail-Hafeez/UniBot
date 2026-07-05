"""
01_extract_text.py

Extract text from every PDF inside data/raw/
Convert them into Markdown files.

Existing Markdown files (WhatsApp knowledge) are copied directly.

Author: Sohail
"""

from pathlib import Path
from datetime import datetime
import logging
import shutil

import fitz
from tqdm import tqdm

from config import *

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "extract_text.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ==========================================================
# File Discovery
# ==========================================================

def find_pdfs(root_folder: Path):
    """
    Recursively find all PDF files.
    """

    return list(root_folder.rglob("*.pdf"))


def find_markdown(root_folder: Path):
    """
    Recursively find all Markdown files.
    """

    return list(root_folder.rglob("*.md"))


# ==========================================================
# Output Path
# ==========================================================

def get_output_path(pdf_path: Path) -> Path:
    """
    Preserve folder structure inside extracted/.
    """

    relative = pdf_path.relative_to(RAW_DIR)

    output = EXTRACTED_DIR / relative

    return output.with_suffix(".md")


# ==========================================================
# Markdown Header
# ==========================================================

def markdown_header(
    title: str,
    source: str,
    filename: str,
    pages: int
):

    today = datetime.now().strftime("%Y-%m-%d")

    return f"""---
title: {title}
source: {source}
filename: {filename}
pages: {pages}
extracted_on: {today}
---

"""

# ==========================================================
# PDF Extraction
# ==========================================================

def extract_pdf_text(pdf_path: Path):
    """
    Extract all text from a PDF.

    Returns
    -------
    tuple
        (text, number_of_pages)
    """

    document = fitz.open(pdf_path)

    text = []

    total_pages = len(document)

    for page in document:

        page_text = page.get_text("text")

        if page_text:
            text.append(page_text.strip())

    document.close()

    return "\n\n".join(text), total_pages


# ==========================================================
# Save Markdown
# ==========================================================

def save_markdown(
    output_path: Path,
    header: str,
    content: str
):
    """
    Save extracted text as Markdown.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(header)
        file.write(content)


# ==========================================================
# Copy Existing Markdown
# ==========================================================

def copy_markdown(md_path: Path):
    """
    Copy existing markdown files
    (e.g. WhatsApp knowledge).
    """

    destination = EXTRACTED_DIR / md_path.relative_to(RAW_DIR)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.copy2(
        md_path,
        destination
    )

    logger.info(f"Copied: {md_path.name}")


# ==========================================================
# Process One PDF
# ==========================================================

def process_pdf(pdf_path: Path):

    try:

        output_path = get_output_path(pdf_path)

        # Skip if already processed
        if output_path.exists():

            logger.info(
                f"Skipped: {pdf_path.name}"
            )

            return

        text, pages = extract_pdf_text(pdf_path)
        if not text.strip():
            logger.warning(f"No text found: {pdf_path.name}")
            return

        header = markdown_header(
            title=pdf_path.stem,
            source=pdf_path.parent.name,
            filename=pdf_path.name,
            pages=pages
        )

        save_markdown(
            output_path,
            header,
            text
        )

        logger.info(
            f"Extracted: {pdf_path.name}"
        )

    except Exception as e:

        logger.error(
            f"Failed: {pdf_path.name}"
        )

        logger.error(str(e))

# ==========================================================
# Process All PDFs
# ==========================================================

def process_all_pdfs():

    pdf_files = find_pdfs(RAW_DIR)

    logger.info(f"Found {len(pdf_files)} PDF files.")

    for pdf in tqdm(
        pdf_files,
        desc="Extracting PDFs"
    ):
        process_pdf(pdf)


# ==========================================================
# Process Markdown Files
# ==========================================================

def process_all_markdown():

    markdown_files = find_markdown(RAW_DIR)

    logger.info(f"Found {len(markdown_files)} Markdown files.")

    for md in tqdm(
        markdown_files,
        desc="Copying Markdown"
    ):

        destination = EXTRACTED_DIR / md.relative_to(RAW_DIR)

        if destination.exists():

            logger.info(
                f"Skipped: {md.name}"
            )

            continue

        copy_markdown(md)


# ==========================================================
# Summary
# ==========================================================

def print_summary():

    pdf_count = len(find_pdfs(RAW_DIR))

    md_count = len(find_markdown(EXTRACTED_DIR))

    logger.info("=" * 60)

    logger.info("Extraction Completed Successfully")

    logger.info(f"PDFs Found        : {pdf_count}")

    logger.info(f"Markdown Produced : {md_count}")

    logger.info("=" * 60)


# ==========================================================
# Main
# ==========================================================

def main():

    logger.info("=" * 60)
    logger.info("University Knowledge Extraction Started")
    logger.info("=" * 60)

    process_all_pdfs()

    process_all_markdown()

    print_summary()


if __name__ == "__main__":

    main()