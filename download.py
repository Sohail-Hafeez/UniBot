"""
00_download_documents.py

Recursively crawls the NUST and MCS download pages,
discovers PDF documents,
downloads them,
and creates document_index.csv.

Author: Sohail
"""

from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import logging
import csv
from tqdm import tqdm

from config import *

# ----------------------------------------------------
# Logging
# ----------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------
# Global Containers
# ----------------------------------------------------

visited_pages = set()

# Dictionary to store unique PDFs
# Key = PDF URL
# Value = PDF information

pdf_links = {}

# ----------------------------------------------------
# Helper Functions
# ----------------------------------------------------

def is_pdf(url: str) -> bool:
    """
    Returns True if url points to a PDF.
    """

    return urlparse(url).path.lower().endswith(".pdf")


def normalize_url(base_url: str, href: str) -> str:
    """
    Converts relative URL to absolute URL.
    """

    return urljoin(base_url, href)


def same_domain(url: str) -> bool:
    """
    Check whether URL belongs to NUST or MCS.
    """

    domain = urlparse(url).netloc.lower()

    return any(
        allowed in domain
        for allowed in ALLOWED_DOMAINS
    )


def download_page(url: str):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        return response.text

    except Exception as e:

        logger.error(f"Cannot open {url}")

        logger.error(str(e))

        return None


def save_pdf(url: str, output_folder: Path):

    try:

        filename = Path(urlparse(url).path).name

        if not filename:
            filename = "document.pdf"

        destination = output_folder / filename

        if destination.exists():

            logger.info(f"Already Exists : {filename}")

            return

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=True
        )

        response.raise_for_status()

        with open(destination, "wb") as file:

            for chunk in response.iter_content(8192):

                file.write(chunk)

        logger.info(f"Downloaded : {filename}")

    except Exception as e:

        logger.error(f"Failed : {url}")

        logger.error(str(e))

# ----------------------------------------------------
# Recursive Crawler
# ----------------------------------------------------

def crawl(url: str, depth: int = 0):
    """
    Recursively crawl pages and collect PDF links.

    Parameters
    ----------
    url : str
        Current page URL.

    depth : int
        Current recursion depth.
    """

    if depth > MAX_DEPTH:
        return

    if url in visited_pages:
        return

    visited_pages.add(url)

    logger.info(f"Crawling: {url}")

    html = download_page(url)

    if html is None:
        return

    soup = BeautifulSoup(html, "lxml")

    links = soup.find_all("a", href=True)

    for link in links:

        href = link.get("href")

        if not href:
            continue

        absolute_url = normalize_url(url, href)

        absolute_url = absolute_url.split("#")[0]

        absolute_url = absolute_url.strip()

        if not same_domain(absolute_url):
            continue

        # -----------------------------------------
        # PDF Found
        # -----------------------------------------

        if is_pdf(absolute_url):

            title = link.get_text(" ", strip=True)

            if not title:
                title = Path(urlparse(absolute_url).path).stem

            # Avoid duplicate PDFs

            if absolute_url not in pdf_links:

                pdf_links[absolute_url] = {
                    "title": title,
                    "url": absolute_url,
                    "filename": Path(urlparse(absolute_url).path).name,
                    "source_page": url,
                    "source": urlparse(absolute_url).netloc
                }

                logger.info(f"Found PDF: {title}")

            continue


        # -----------------------------------------
        # Crawl Next Page
        # -----------------------------------------

        crawl(
            absolute_url,
            depth + 1
        )

# ----------------------------------------------------
# Save CSV Index
# ----------------------------------------------------

def save_document_index():

    logger.info("Saving document index...")

    with open(
        DOCUMENT_INDEX,
        "w",
        newline="",
        encoding="utf-8"
    ) as csvfile:

        writer = csv.writer(csvfile)

        writer.writerow([
            "Title",
            "Filename",
            "URL",
            "Source",
            "Discovered From"
        ])

        for pdf in pdf_links.values():

            writer.writerow([
                pdf["title"],
                pdf["filename"],
                pdf["url"],
                pdf["source"],
                pdf["source_page"]
            ])

    logger.info(f"Saved {len(pdf_links)} records.")


# ----------------------------------------------------
# Download PDFs
# ----------------------------------------------------

def download_all_pdfs():

    logger.info("Starting PDF Downloads...")

    for pdf in tqdm(pdf_links.values()):

        source = pdf["source"].lower()

        if "mcs" in source:

            output_folder = MCS_DIR

        else:

            output_folder = NUST_DIR

        save_pdf(
            pdf["url"],
            output_folder
        )


# ----------------------------------------------------
# Main
# ----------------------------------------------------

def main():

    logger.info("=" * 60)
    logger.info("University Document Downloader Started")
    logger.info("=" * 60)

    for website in WEBSITES:

        logger.info(f"Crawling {website['name']}")

        crawl(website["url"])

    logger.info("-" * 60)
    logger.info(f"Total PDFs Found : {len(pdf_links)}")

    save_document_index()

    download_all_pdfs()

    logger.info("=" * 60)
    logger.info("Completed Successfully")
    logger.info("=" * 60)


if __name__ == "__main__":

    main()
