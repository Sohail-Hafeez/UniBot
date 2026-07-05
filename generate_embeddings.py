"""
04_embeddings.py

Batch embedding generation using Mistral AI's `mistral-embed` model.

Reads chunked JSONL files from data/chunked/, generates embeddings
in batches, and saves the results as JSONL in data/embeddings/.

Features:
    - Batch processing via utils.llm.embed_texts (auto-splits oversized
      batches, retries transient failures with exponential backoff)
    - Cost tracking and logging
    - Skip already-embedded documents
    - Progress bars per batch

Author: Sohail
"""

import json
import logging
import time
from pathlib import Path

from tqdm import tqdm

from config import (
    CHUNK_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIR,
    EMBEDDING_LOG,
    EMBEDDING_MODEL,
    PRICING,
)
from utils.llm import embed_texts

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(EMBEDDING_LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ==========================================================
# Cost Estimation
# ==========================================================

def estimate_embedding_cost(total_tokens: int) -> float:
    """
    Estimate the embedding cost in USD.

    Parameters
    ----------
    total_tokens : int
        Total input tokens processed.

    Returns
    -------
    float
        Cost in USD.
    """

    pricing = PRICING.get(EMBEDDING_MODEL, {"input": 0.10})

    return round((total_tokens / 1_000_000) * pricing["input"], 8)


# ==========================================================
# Load All Chunks
# ==========================================================

def load_all_chunks() -> list[dict]:
    """
    Load all chunk dicts from JSONL files in data/chunked/.

    Returns
    -------
    list[dict]
        List of all chunk dicts across all documents.
    """

    jsonl_files = sorted(CHUNK_DIR.rglob("*.jsonl"))

    logger.info("Found %d JSONL chunk files.", len(jsonl_files))

    all_chunks: list[dict] = []

    for jsonl_path in jsonl_files:
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_chunks.append(json.loads(line))

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Error reading %s: %s", jsonl_path.name, str(e)
            )

    logger.info("Loaded %d total chunks.", len(all_chunks))
    return all_chunks


# ==========================================================
# Load Already-Embedded Chunk IDs
# ==========================================================

def load_embedded_ids() -> set[str]:
    """
    Scan existing embedding JSONL files and collect chunk IDs
    that have already been embedded.

    Returns
    -------
    set[str]
        Set of chunk_id strings already embedded.
    """

    existing_ids: set[str] = set()

    for jsonl_path in EMBEDDING_DIR.rglob("*.jsonl"):
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        chunk_id = data.get("chunk_id", "")
                        if chunk_id:
                            existing_ids.add(chunk_id)

        except (json.JSONDecodeError, OSError):
            pass

    if existing_ids:
        logger.info("Found %d already-embedded chunks.", len(existing_ids))

    return existing_ids


# ==========================================================
# Process All Embeddings
# ==========================================================

def generate_all_embeddings() -> dict:
    """
    Generate embeddings for all chunks, skipping already-embedded ones.

    Saves results as JSONL grouped by source document.

    Returns
    -------
    dict
        Summary statistics.
    """

    # Load chunks and filter out already-embedded
    all_chunks = load_all_chunks()
    embedded_ids = load_embedded_ids()

    pending_chunks = [
        c for c in all_chunks
        if c.get("chunk_id", "") not in embedded_ids
    ]

    logger.info(
        "Chunks to embed: %d (skipping %d already done).",
        len(pending_chunks),
        len(all_chunks) - len(pending_chunks),
    )

    if not pending_chunks:
        logger.info("All chunks already embedded. Nothing to do.")
        return {
            "total_chunks": len(all_chunks),
            "newly_embedded": 0,
            "skipped": len(all_chunks),
            "total_tokens": 0,
            "estimated_cost": 0.0,
        }

    stats = {
        "total_chunks": len(all_chunks),
        "newly_embedded": 0,
        "skipped": len(all_chunks) - len(pending_chunks),
        "failed_batches": 0,
        "total_tokens": 0,
        "estimated_cost": 0.0,
    }

    # Group chunks by source file for organized output
    source_groups: dict[str, list[dict]] = {}

    for chunk in pending_chunks:
        source = chunk.get("source_file", "unknown")

        if source not in source_groups:
            source_groups[source] = []

        source_groups[source].append(chunk)

    # Process in batches within each source group
    total_batches = (len(pending_chunks) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    batch_progress = tqdm(
        total=len(pending_chunks),
        desc="Generating embeddings",
    )

    for source_file, chunks in source_groups.items():

        embedded_chunks: list[dict] = []

        # Process this source's chunks in batches
        for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):

            batch = chunks[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
            texts = [c["text"] for c in batch]

            try:
                embeddings, tokens_used = embed_texts(texts, model=EMBEDDING_MODEL)

                stats["total_tokens"] += tokens_used

                # Pair each chunk with its embedding
                for chunk, embedding in zip(batch, embeddings):
                    embedded_chunk = {
                        "chunk_id": chunk["chunk_id"],
                        "document_title": chunk.get("document_title", ""),
                        "category": chunk.get("category", "Other"),
                        "topics": chunk.get("topics", []),
                        "source_file": chunk.get("source_file", ""),
                        "section_heading": chunk.get("section_heading", ""),
                        "chunk_number": chunk.get("chunk_number", 0),
                        "text": chunk["text"],
                        "word_count": chunk.get("word_count", 0),
                        "estimated_tokens": chunk.get("estimated_tokens", 0),
                        "embedding": embedding,
                    }

                    embedded_chunks.append(embedded_chunk)
                    stats["newly_embedded"] += 1

                batch_progress.update(len(batch))

            except Exception as e:
                logger.error(
                    "Batch embedding failed for %s (batch %d): %s",
                    source_file,
                    batch_start // EMBEDDING_BATCH_SIZE + 1,
                    str(e),
                )
                stats["failed_batches"] += 1
                batch_progress.update(len(batch))

        # Save all embedded chunks for this source as JSONL
        if embedded_chunks:
            _save_embedded_chunks(embedded_chunks, source_file)

    batch_progress.close()

    # Calculate cost
    stats["estimated_cost"] = estimate_embedding_cost(stats["total_tokens"])

    return stats


# ==========================================================
# Save Embedded Chunks
# ==========================================================

def _save_embedded_chunks(
    chunks: list[dict],
    source_file: str,
) -> Path:
    """
    Save embedded chunks as JSONL, preserving directory structure.

    Parameters
    ----------
    chunks : list[dict]
        Chunks with embedding vectors.
    source_file : str
        Relative source file path.

    Returns
    -------
    Path
        Output JSONL file path.
    """

    relative = Path(source_file)
    output_path = (EMBEDDING_DIR / relative).with_suffix(".jsonl")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info(
        "Saved %d embeddings → %s",
        len(chunks),
        output_path.name,
    )

    return output_path


# ==========================================================
# Print Summary
# ==========================================================

def print_summary(stats: dict) -> None:
    """Log a formatted summary of the embedding run."""

    logger.info("=" * 60)
    logger.info("EMBEDDING GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info("Total Chunks      : %d", stats["total_chunks"])
    logger.info("Newly Embedded    : %d", stats["newly_embedded"])
    logger.info("Already Done      : %d", stats["skipped"])
    logger.info("Failed Batches    : %d", stats.get("failed_batches", 0))
    logger.info("Total Tokens      : %d", stats["total_tokens"])
    logger.info("Estimated Cost    : $%.6f", stats["estimated_cost"])
    logger.info("=" * 60)


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """Entry point for the embedding generation pipeline stage."""

    logger.info("=" * 60)
    logger.info("Embedding Generator Started")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    stats = generate_all_embeddings()

    elapsed = round(time.perf_counter() - start_time, 1)
    logger.info("Total embedding time: %.1fs", elapsed)

    print_summary(stats)


if __name__ == "__main__":
    main()
