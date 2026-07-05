"""
02_ai_analyser.py

Reads every extracted markdown file and uses a Mistral AI chat model to
analyse whether the document is useful for the university chatbot.

Uses Mistral's `json_schema` structured output mode (via utils.llm) to
guarantee valid JSON — no "return ONLY JSON" prompting needed.

Outputs one metadata JSON file per document inside data/metadata/.

Author: Sohail
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from tqdm import tqdm

from config import (
    ALLOWED_CATEGORIES,
    ANALYSER_LOG,
    EXTRACTED_DIR,
    LOG_DIR,
    METADATA_DIR,
)
from utils.llm import ask_llm_json

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(ANALYSER_LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ==========================================================
# Constants
# ==========================================================

MAX_HEAD_CHARS = 4000   # First N characters to sample
MAX_TAIL_CHARS = 2000   # Last N characters to sample


# ==========================================================
# Pydantic Schema for Structured Output
# ==========================================================

class DocumentAnalysis(BaseModel):
    """
    Schema for the LLM's document analysis response.

    Passed directly to the OpenAI Responses API as a json_schema
    so the model is forced to return exactly this structure.
    """

    title: str = Field(
        description="A concise, descriptive title for the document."
    )

    useful: bool = Field(
        description=(
            "Whether the document is useful for the university "
            "chatbot knowledge base."
        )
    )

    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0."
    )

    category: str = Field(
        description=(
            "Single category from the allowed list: "
            + ", ".join(ALLOWED_CATEGORIES)
        )
    )

    audience: str = Field(
        description=(
            "Target audience, e.g. 'undergraduate students', "
            "'postgraduate students', 'all students'."
        )
    )

    topics: list[str] = Field(
        description="List of 2-5 key topics covered in the document."
    )

    summary: str = Field(
        description="A 2-3 sentence summary of the document content."
    )

    reason: str = Field(
        description=(
            "Brief explanation of why the document is or is not "
            "useful for newly admitted students."
        )
    )


# ==========================================================
# File Discovery
# ==========================================================

def find_markdown_files() -> list[Path]:
    """
    Recursively discover all markdown files in the extracted directory.

    Returns
    -------
    list[Path]
        Sorted list of markdown file paths.
    """

    files = sorted(EXTRACTED_DIR.rglob("*.md"))

    logger.info("Found %d markdown files in %s", len(files), EXTRACTED_DIR)

    return files


# ==========================================================
# Read Document Sample
# ==========================================================

def load_document_sample(md_file: Path) -> str:
    """
    Read a representative sample from a markdown file.

    For short documents (≤6000 chars), returns the full text.
    For longer documents, returns the first 4000 and last 2000
    characters with an ellipsis separator.

    Parameters
    ----------
    md_file : Path
        Path to the markdown file.

    Returns
    -------
    str
        The document sample text.
    """

    text = md_file.read_text(encoding="utf-8")

    if len(text) <= (MAX_HEAD_CHARS + MAX_TAIL_CHARS):
        return text

    head = text[:MAX_HEAD_CHARS]
    tail = text[-MAX_TAIL_CHARS:]

    return f"{head}\n\n[... content truncated for analysis ...]\n\n{tail}"


# ==========================================================
# Output Path
# ==========================================================

def get_metadata_path(md_file: Path) -> Path:
    """
    Compute the metadata JSON output path, preserving the
    folder structure from extracted/ into metadata/.

    Parameters
    ----------
    md_file : Path
        Path to the source markdown file.

    Returns
    -------
    Path
        Corresponding metadata JSON path.
    """

    relative = md_file.relative_to(EXTRACTED_DIR)

    return (METADATA_DIR / relative).with_suffix(".json")


# ==========================================================
# Prompt Builder
# ==========================================================

def build_analysis_prompt(document_sample: str, source_folder: str) -> str:
    """
    Build the analysis prompt for the LLM.

    The prompt does NOT ask the model to "return JSON" because
    we use structured output via the Responses API json_schema.

    Parameters
    ----------
    document_sample : str
        The representative text sample from the document.
    source_folder : str
        Top-level folder the document was sourced from ("NUST", "MCS",
        or "Whatsapp") — a strong prior for whether it's likely to be
        campus-specific to NUST's main campus vs. MCS vs. campus-agnostic.

    Returns
    -------
    str
        The complete prompt string.
    """

    categories_str = ", ".join(ALLOWED_CATEGORIES)

    return f"""You are an expert university document analyst.

You are building a knowledge base for a chatbot that helps newly
admitted students at MCS (Military College of Signals).

IMPORTANT CONTEXT — READ CAREFULLY:
MCS is a constituent college of NUST (National University of Sciences
and Technology), physically located in Lalkurti, Rawalpindi. This is a
SEPARATE CAMPUS from NUST's main campus in H-12, Islamabad. Hostel
arrangements, mess/dining facilities, recreational facilities (gyms,
pools, clubs), transport, orientation events, and day-to-day campus-life
rules DIFFER between the two campuses — content correct for H-12 can be
actively wrong or misleading if presented to an MCS student.

This document was sourced from the "{source_folder}" downloads page.

Analyse the following document and determine:

1. Whether it is useful for newly admitted MCS students specifically.
2. What category it belongs to.
3. A brief summary and key topics.

A document is useful if:
- It is genuinely MCS-specific (hostel, facilities, transport, campus
  life, orientation, rules — as experienced AT MCS Lalkurti), OR
- It describes a NUST-wide/university-level policy or process that
  applies uniformly across all constituent colleges including MCS,
  e.g. admissions criteria, examination regulations, degree/transcript
  requirements, university-wide fee structure or scholarship policy,
  code of conduct, academic calendar, administrative forms.

A document is NOT useful if:
- It describes campus-specific facilities, hostel rules/fees,
  mess/dining, transport routes, sports/recreation facilities
  (gym, pool, bowling alley, saddle club, etc.), or campus-life
  logistics that are SPECIFIC TO NUST's H-12 Islamabad main campus and
  would be wrong or misleading for an MCS Lalkurti student.
- It is a stale one-off event schedule, sports draw/fixture list, or
  newsletter with mostly general news (low value for a student FAQ bot
  regardless of campus).
- It is a course outline or syllabus for a specific course.
- A faculty/staff recruitment notice.
- A tender, procurement, or vendor document.
- A research paper or technical publication.
- When in doubt about whether a "Hostel", "Campus Facilities",
  "Campus Life", "Orientation", or "Transport" document applies to
  MCS or only to NUST H-12, prefer marking it NOT useful rather than
  risk giving MCS students information about a campus they don't
  attend.

Choose exactly ONE category from:
{categories_str}

Document:

{document_sample}"""


# ==========================================================
# Analyse Single Document
# ==========================================================

def analyse_document(md_file: Path) -> Optional[dict]:
    """
    Analyse a single markdown document using the LLM.

    Parameters
    ----------
    md_file : Path
        Path to the extracted markdown file.

    Returns
    -------
    dict or None
        Complete metadata dict if successful, None on failure.
    """

    try:
        # Load representative sample
        sample = load_document_sample(md_file)

        if not sample.strip():
            logger.warning("Empty document: %s", md_file.name)
            return None

        # Top-level folder ("NUST", "MCS", "Whatsapp") — tells the model
        # which downloads page this came from.
        source_folder = md_file.relative_to(EXTRACTED_DIR).parts[0]

        # Build prompt
        prompt = build_analysis_prompt(sample, source_folder)

        # Call LLM with structured output
        result = ask_llm_json(
            prompt=prompt,
            schema=DocumentAnalysis,
            temperature=0.0,
        )

        # Extract LLM response
        analysis = result["response"]

        # Compute the relative source path for metadata
        relative_source = str(md_file.relative_to(EXTRACTED_DIR))

        # Build complete metadata record
        metadata = {
            "title": analysis.get("title", md_file.stem),
            "useful": analysis.get("useful", False),
            "confidence": analysis.get("confidence", 0.0),
            "category": analysis.get("category", "Other"),
            "audience": analysis.get("audience", ""),
            "topics": analysis.get("topics", []),
            "summary": analysis.get("summary", ""),
            "reason": analysis.get("reason", ""),
            "source_file": relative_source,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processing_time": result["time"],
            "token_usage": result["usage"],
            "estimated_cost": result["cost"],
        }

        return metadata

    except Exception as e:
        logger.error(
            "Failed to analyse %s: %s",
            md_file.name,
            str(e),
        )
        return None


# ==========================================================
# Save Metadata
# ==========================================================

def save_metadata(output_path: Path, metadata: dict) -> None:
    """
    Save a metadata dict as a formatted JSON file.

    Parameters
    ----------
    output_path : Path
        Destination file path.
    metadata : dict
        The metadata to save.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(metadata, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


# ==========================================================
# Process All Documents
# ==========================================================

def process_all_documents() -> dict:
    """
    Iterate through all extracted markdown files, analyse each
    with the LLM, and save metadata JSON files.

    Skips documents that already have a metadata JSON file.

    Returns
    -------
    dict
        Summary statistics with keys:
        total, processed, skipped, useful, not_useful, failed.
    """

    markdown_files = find_markdown_files()

    stats = {
        "total": len(markdown_files),
        "processed": 0,
        "skipped": 0,
        "useful": 0,
        "not_useful": 0,
        "failed": 0,
        "total_cost": 0.0,
        "total_time": 0.0,
    }

    for md_file in tqdm(markdown_files, desc="Analysing documents"):

        output_path = get_metadata_path(md_file)

        # Skip already-processed documents
        if output_path.exists():
            stats["skipped"] += 1
            continue

        # Analyse the document
        metadata = analyse_document(md_file)

        if metadata is None:
            stats["failed"] += 1
            continue

        # Save metadata
        save_metadata(output_path, metadata)

        # Update statistics
        stats["processed"] += 1
        stats["total_cost"] += metadata.get("estimated_cost", 0.0)
        stats["total_time"] += metadata.get("processing_time", 0.0)

        if metadata.get("useful", False):
            stats["useful"] += 1
        else:
            stats["not_useful"] += 1

        logger.info(
            "Analysed: %s | useful=%s | category=%s",
            md_file.name,
            metadata.get("useful"),
            metadata.get("category"),
        )

    return stats


# ==========================================================
# Print Summary
# ==========================================================

def print_summary(stats: dict) -> None:
    """
    Log a formatted summary of the analysis run.
    """

    logger.info("=" * 60)
    logger.info("AI ANALYSIS COMPLETE")
    logger.info("=" * 60)
    logger.info("Total Documents   : %d", stats["total"])
    logger.info("Already Processed : %d", stats["skipped"])
    logger.info("Newly Processed   : %d", stats["processed"])
    logger.info("Useful            : %d", stats["useful"])
    logger.info("Not Useful        : %d", stats["not_useful"])
    logger.info("Failed            : %d", stats["failed"])
    logger.info("Total Cost        : $%.4f", stats["total_cost"])
    logger.info("Total Time        : %.1fs", stats["total_time"])
    logger.info("=" * 60)


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """Entry point for the AI analyser pipeline stage."""

    logger.info("=" * 60)
    logger.info("University Document AI Analyser Started")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    stats = process_all_documents()

    total_elapsed = round(time.perf_counter() - start_time, 1)
    stats["total_time"] = total_elapsed

    print_summary(stats)


if __name__ == "__main__":
    main()
