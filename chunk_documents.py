"""
03_chunk_documents.py

Intelligent, heading-aware document chunker for the RAG pipeline.

Reads metadata to identify useful documents, then splits their
markdown content into semantically meaningful chunks based on
headings, sections, lists, and paragraph boundaries.

Never splits blindly — respects document structure.

Output: JSONL files in data/chunked/ with rich metadata per chunk.

Author: Sohail
"""

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import tiktoken
from tqdm import tqdm

from config import (
    CHUNK_DIR,
    CHUNK_OVERLAP_TOKENS,
    CHUNKER_LOG,
    EXTRACTED_DIR,
    MAX_CHUNK_TOKENS,
    METADATA_DIR,
    MIN_CHUNK_TOKENS,
)

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(CHUNKER_LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ==========================================================
# Token Encoder (singleton)
# ==========================================================

_encoder: Optional[tiktoken.Encoding] = None


def _get_encoder() -> tiktoken.Encoding:
    """
    Returns a lazily-initialised tiktoken encoder (cl100k_base).
    This is the encoding used by GPT-4, GPT-4-turbo, and GPT-4.1.
    """
    global _encoder

    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
        logger.info("Tiktoken encoder initialised (cl100k_base).")

    return _encoder


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(_get_encoder().encode(text))


# ==========================================================
# Metadata Loading
# ==========================================================

def load_useful_metadata() -> list[dict]:
    """
    Scan all metadata JSON files and return only those
    where useful == true.

    Returns
    -------
    list[dict]
        List of metadata dicts for useful documents.
    """

    metadata_files = sorted(METADATA_DIR.rglob("*.json"))

    useful_docs = []

    for meta_path in metadata_files:
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))

            if data.get("useful", False):
                useful_docs.append(data)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Cannot read metadata %s: %s",
                meta_path.name,
                str(e),
            )

    logger.info(
        "Found %d useful documents out of %d total metadata files.",
        len(useful_docs),
        len(metadata_files),
    )

    return useful_docs


# ==========================================================
# Markdown Section Splitter
# ==========================================================

# Matches markdown headings: # H1, ## H2, ### H3, etc.
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def split_into_sections(text: str) -> list[dict]:
    """
    Split markdown text into sections based on headings.

    Each section contains a heading (or "Introduction" for content
    before the first heading) and the body text under it.

    Parameters
    ----------
    text : str
        Full markdown text content.

    Returns
    -------
    list[dict]
        List of dicts with keys: "heading", "level", "text".
    """

    sections: list[dict] = []

    # Find all heading positions
    headings = list(HEADING_PATTERN.finditer(text))

    if not headings:
        # No headings found — treat entire document as one section
        return [{"heading": "Document Content", "level": 0, "text": text.strip()}]

    # Content before first heading
    pre_heading_text = text[: headings[0].start()].strip()

    if pre_heading_text:
        sections.append({
            "heading": "Introduction",
            "level": 0,
            "text": pre_heading_text,
        })

    # Process each heading and its content
    for i, match in enumerate(headings):

        heading_level = len(match.group(1))
        heading_text = match.group(2).strip()

        # Content starts after the heading line
        content_start = match.end()

        # Content ends at the next heading or end of text
        if i + 1 < len(headings):
            content_end = headings[i + 1].start()
        else:
            content_end = len(text)

        body = text[content_start:content_end].strip()

        if heading_text or body:
            sections.append({
                "heading": heading_text,
                "level": heading_level,
                "text": body,
            })

    return sections


# ==========================================================
# Paragraph-Level Splitting
# ==========================================================

def split_into_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs on double newlines.
    Preserves list items as part of their paragraph.

    Parameters
    ----------
    text : str
        The section text to split.

    Returns
    -------
    list[str]
        Non-empty paragraph strings.
    """

    # Split on blank lines (two or more newlines)
    raw_paragraphs = re.split(r"\n\s*\n", text)

    # Filter out empty paragraphs
    return [p.strip() for p in raw_paragraphs if p.strip()]


# ==========================================================
# Chunk Builder
# ==========================================================

def build_chunks_from_section(
    section_heading: str,
    section_text: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """
    Split a section's text into token-bounded chunks.

    Strategy:
        1. Split section into paragraphs.
        2. Greedily accumulate paragraphs into a chunk until
           adding the next paragraph would exceed max_tokens.
        3. If a single paragraph exceeds max_tokens, split it
           on sentence boundaries.
        4. Apply overlap by carrying the last ~overlap_tokens
           from the previous chunk into the next.

    Parameters
    ----------
    section_heading : str
        The heading for context (not included in chunk text).
    section_text : str
        The section body text.
    max_tokens : int
        Maximum tokens per chunk.
    overlap_tokens : int
        Approximate overlap between consecutive chunks.

    Returns
    -------
    list[str]
        List of chunk text strings.
    """

    if not section_text.strip():
        return []

    paragraphs = split_into_paragraphs(section_text)

    if not paragraphs:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:

        para_tokens = count_tokens(paragraph)

        # Case 1: Paragraph fits in current chunk
        if current_tokens + para_tokens <= max_tokens:
            current_parts.append(paragraph)
            current_tokens += para_tokens
            continue

        # Case 2: Current chunk is non-empty — flush it
        if current_parts:
            chunks.append("\n\n".join(current_parts))

            # Calculate overlap: keep trailing text from flushed chunk
            overlap_text = _get_overlap_text(
                current_parts, overlap_tokens
            )

            current_parts = [overlap_text] if overlap_text else []
            current_tokens = count_tokens(overlap_text) if overlap_text else 0

        # Case 3: Single paragraph exceeds max_tokens — split on sentences
        if para_tokens > max_tokens:
            sentence_chunks = _split_long_paragraph(
                paragraph, max_tokens, overlap_tokens
            )

            for sc in sentence_chunks:
                chunks.append(sc)

            # Carry overlap from last sentence chunk
            if chunks:
                overlap_text = _get_overlap_from_text(
                    chunks[-1], overlap_tokens
                )

                if overlap_text:
                    current_parts = [overlap_text]
                    current_tokens = count_tokens(overlap_text)

        else:
            # Paragraph fits on its own — start new chunk
            current_parts.append(paragraph)
            current_tokens = count_tokens(paragraph)

    # Flush remaining content
    if current_parts:
        remaining = "\n\n".join(current_parts)

        if count_tokens(remaining) >= MIN_CHUNK_TOKENS:
            chunks.append(remaining)
        elif chunks:
            # Merge small remainder into last chunk
            chunks[-1] = chunks[-1] + "\n\n" + remaining
        else:
            chunks.append(remaining)

    return chunks


def _get_overlap_text(parts: list[str], target_tokens: int) -> str:
    """
    Extract approximately target_tokens worth of text from the
    end of a list of paragraph parts for overlap.
    """

    overlap_parts: list[str] = []
    token_count = 0

    for part in reversed(parts):
        part_tokens = count_tokens(part)

        if token_count + part_tokens > target_tokens:
            # Take partial — split into sentences and take from end
            sentences = re.split(r"(?<=[.!?])\s+", part)

            for sentence in reversed(sentences):
                s_tokens = count_tokens(sentence)

                if token_count + s_tokens <= target_tokens:
                    overlap_parts.insert(0, sentence)
                    token_count += s_tokens
                else:
                    break

            break

        overlap_parts.insert(0, part)
        token_count += part_tokens

    return " ".join(overlap_parts) if overlap_parts else ""


def _get_overlap_from_text(text: str, target_tokens: int) -> str:
    """
    Extract approximately target_tokens from the end of a text string.
    Splits on sentence boundaries.
    """

    sentences = re.split(r"(?<=[.!?])\s+", text)

    overlap_parts: list[str] = []
    token_count = 0

    for sentence in reversed(sentences):
        s_tokens = count_tokens(sentence)

        if token_count + s_tokens > target_tokens:
            break

        overlap_parts.insert(0, sentence)
        token_count += s_tokens

    return " ".join(overlap_parts) if overlap_parts else ""


def _split_long_paragraph(
    paragraph: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """
    Split an oversized paragraph into chunks on sentence boundaries.
    Falls back to word-level splitting if sentences are too long.
    """

    # Try sentence-level splitting first
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)

    if len(sentences) <= 1:
        # No sentence boundaries — fall back to word splitting
        return _split_by_words(paragraph, max_tokens)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for sentence in sentences:

        s_tokens = count_tokens(sentence)

        if current_tokens + s_tokens <= max_tokens:
            current_parts.append(sentence)
            current_tokens += s_tokens
        else:
            if current_parts:
                chunks.append(" ".join(current_parts))

            if s_tokens > max_tokens:
                # Even a single sentence is too long — word split
                chunks.extend(_split_by_words(sentence, max_tokens))
                current_parts = []
                current_tokens = 0
            else:
                current_parts = [sentence]
                current_tokens = s_tokens

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


def _split_by_words(text: str, max_tokens: int) -> list[str]:
    """
    Last-resort splitting: break text into word groups that
    fit within the token limit.
    """

    words = text.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_tokens = 0

    for word in words:
        w_tokens = count_tokens(word)

        if current_tokens + w_tokens <= max_tokens:
            current_words.append(word)
            current_tokens += w_tokens
        else:
            if current_words:
                chunks.append(" ".join(current_words))
            current_words = [word]
            current_tokens = w_tokens

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


# ==========================================================
# Generate Chunk ID
# ==========================================================

def generate_chunk_id(source_file: str, chunk_number: int) -> str:
    """
    Generate a deterministic, globally unique chunk ID from the source
    file and chunk number.

    The filename stem alone is NOT sufficient: NUST and MCS mirror several
    identically-named forms in different folders (e.g. both
    "MCS/PAPER-RECHECKING-FORM.md" and "NUST/PAPER-RECHECKING-FORM.md"
    exist). Using only the stem would make their chunk IDs collide, which
    silently overwrites points when upserted into Qdrant. A short hash of
    the full relative path guarantees uniqueness regardless of filename
    length or truncation, while the stem prefix keeps IDs human-readable.

    Example: "PAPER_RECHECKING_FORM_5e93a1c2_0001"
    """

    base = Path(source_file).stem

    clean = re.sub(r"[^a-zA-Z0-9]", "_", base)
    clean = re.sub(r"_+", "_", clean).strip("_")

    if len(clean) > 50:
        clean = clean[:50]

    path_hash = hashlib.sha1(source_file.encode("utf-8")).hexdigest()[:8]

    return f"{clean}_{path_hash}_{chunk_number:04d}"


# ==========================================================
# Process Single Document
# ==========================================================

def chunk_document(metadata: dict) -> list[dict]:
    """
    Chunk a single document based on its metadata.

    Parameters
    ----------
    metadata : dict
        Document metadata (must include source_file, title,
        category, topics).

    Returns
    -------
    list[dict]
        List of chunk dicts ready for JSONL output.
    """

    source_file = metadata["source_file"]
    md_path = EXTRACTED_DIR / source_file

    if not md_path.exists():
        logger.error("Source file not found: %s", md_path)
        return []

    # Read full document text
    text = md_path.read_text(encoding="utf-8")

    if not text.strip():
        logger.warning("Empty document: %s", source_file)
        return []

    # Strip YAML frontmatter if present (between --- markers)
    frontmatter_pattern = r"^---\s*\n.*?\n---\s*\n"
    text = re.sub(frontmatter_pattern, "", text, count=1, flags=re.DOTALL)

    # Split into sections by headings
    sections = split_into_sections(text)

    # Generate chunks for each section
    all_chunks: list[dict] = []
    chunk_number = 1

    for section in sections:

        section_heading = section["heading"]
        section_text = section["text"]

        # Build token-bounded chunks from this section
        chunk_texts = build_chunks_from_section(
            section_heading=section_heading,
            section_text=section_text,
        )

        for chunk_text in chunk_texts:

            if not chunk_text.strip():
                continue

            word_count = len(chunk_text.split())
            token_count = count_tokens(chunk_text)

            chunk = {
                "chunk_id": generate_chunk_id(source_file, chunk_number),
                "document_title": metadata.get("title", ""),
                "category": metadata.get("category", "Other"),
                "topics": metadata.get("topics", []),
                "source_file": source_file,
                "section_heading": section_heading,
                "chunk_number": chunk_number,
                "text": chunk_text,
                "word_count": word_count,
                "estimated_tokens": token_count,
            }

            all_chunks.append(chunk)
            chunk_number += 1

    return all_chunks


# ==========================================================
# Save Chunks as JSONL
# ==========================================================

def save_chunks_jsonl(
    chunks: list[dict],
    source_file: str,
) -> Path:
    """
    Save chunks for a single document as a JSONL file.

    Parameters
    ----------
    chunks : list[dict]
        List of chunk dicts.
    source_file : str
        Relative source file path (used to compute output path).

    Returns
    -------
    Path
        The output JSONL file path.
    """

    relative = Path(source_file)
    output_path = (CHUNK_DIR / relative).with_suffix(".jsonl")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    return output_path


# ==========================================================
# Process All Documents
# ==========================================================

def process_all_documents() -> dict:
    """
    Load useful metadata, chunk each document, and save JSONL output.

    Returns
    -------
    dict
        Summary statistics.
    """

    useful_docs = load_useful_metadata()

    stats = {
        "total_documents": len(useful_docs),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "total_chunks": 0,
        "total_tokens": 0,
    }

    for metadata in tqdm(useful_docs, desc="Chunking documents"):

        source_file = metadata.get("source_file", "")

        # Check if already chunked
        output_path = (CHUNK_DIR / Path(source_file)).with_suffix(".jsonl")

        if output_path.exists():
            stats["skipped"] += 1
            continue

        try:
            chunks = chunk_document(metadata)

            if not chunks:
                stats["failed"] += 1
                continue

            save_chunks_jsonl(chunks, source_file)

            stats["processed"] += 1
            stats["total_chunks"] += len(chunks)
            stats["total_tokens"] += sum(
                c.get("estimated_tokens", 0) for c in chunks
            )

            logger.info(
                "Chunked: %s → %d chunks",
                source_file,
                len(chunks),
            )

        except Exception as e:
            logger.error("Failed to chunk %s: %s", source_file, str(e))
            stats["failed"] += 1

    return stats


# ==========================================================
# Print Summary
# ==========================================================

def print_summary(stats: dict) -> None:
    """Log a formatted summary of the chunking run."""

    avg_tokens = 0

    if stats["total_chunks"] > 0:
        avg_tokens = stats["total_tokens"] // stats["total_chunks"]

    logger.info("=" * 60)
    logger.info("CHUNKING COMPLETE")
    logger.info("=" * 60)
    logger.info("Useful Documents  : %d", stats["total_documents"])
    logger.info("Newly Processed   : %d", stats["processed"])
    logger.info("Already Chunked   : %d", stats["skipped"])
    logger.info("Failed            : %d", stats["failed"])
    logger.info("Total Chunks      : %d", stats["total_chunks"])
    logger.info("Total Tokens      : %d", stats["total_tokens"])
    logger.info("Avg Tokens/Chunk  : %d", avg_tokens)
    logger.info("=" * 60)


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """Entry point for the document chunker pipeline stage."""

    logger.info("=" * 60)
    logger.info("Document Chunker Started")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    stats = process_all_documents()

    elapsed = round(time.perf_counter() - start_time, 1)
    logger.info("Total chunking time: %.1fs", elapsed)

    print_summary(stats)


if __name__ == "__main__":
    main()
