"""
05_qdrant_upload.py

Upload embeddings to Qdrant vector database.

Reads embedded JSONL files from data/embeddings/, creates
(or recreates) a Qdrant collection, and upserts all points
in batches.

Each point contains:
    - A 1536-dimensional embedding vector
    - Payload: title, category, topics, source, chunk_id,
      section, text

Author: Sohail
"""

import json
import logging
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)
from tqdm import tqdm

from config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_DIR,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_LOG,
    QDRANT_URL,
)

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(QDRANT_LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ==========================================================
# Constants
# ==========================================================

UPSERT_BATCH_SIZE = 100     # Points per upsert call


# ==========================================================
# Qdrant Client
# ==========================================================

def create_qdrant_client() -> QdrantClient:
    """
    Create and return a Qdrant client.

    Uses QDRANT_URL and QDRANT_API_KEY from config.
    Falls back to localhost if no URL is configured.

    Returns
    -------
    QdrantClient
        Connected Qdrant client.

    Raises
    ------
    ConnectionError
        If Qdrant is unreachable.
    """

    logger.info("Connecting to Qdrant at %s", QDRANT_URL)

    kwargs = {"url": QDRANT_URL, "timeout": 60}

    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY

    client = QdrantClient(**kwargs)

    # Verify connection
    try:
        collections = client.get_collections()
        logger.info(
            "Connected to Qdrant. Existing collections: %d",
            len(collections.collections),
        )
    except Exception as e:
        raise ConnectionError(
            f"Cannot connect to Qdrant at {QDRANT_URL}. "
            f"Make sure Qdrant is running. Error: {e}"
        ) from e

    return client


# ==========================================================
# Collection Management
# ==========================================================

def ensure_collection(client: QdrantClient) -> None:
    """
    Create the Qdrant collection if it doesn't exist.

    If it exists, logs a warning and continues (no recreation
    to avoid data loss in production).

    Parameters
    ----------
    client : QdrantClient
        Connected Qdrant client.
    """

    existing = [
        c.name for c in client.get_collections().collections
    ]

    if QDRANT_COLLECTION in existing:
        logger.info(
            "Collection '%s' already exists. Will upsert into it.",
            QDRANT_COLLECTION,
        )
        return

    logger.info("Creating collection '%s'...", QDRANT_COLLECTION)

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=EMBEDDING_DIMENSIONS,
            distance=Distance.COSINE,
        ),
    )

    logger.info(
        "Collection '%s' created (dim=%d, distance=cosine).",
        QDRANT_COLLECTION,
        EMBEDDING_DIMENSIONS,
    )


# ==========================================================
# Deterministic UUID from Chunk ID
# ==========================================================

def chunk_id_to_uuid(chunk_id: str) -> str:
    """
    Generate a deterministic UUID from a chunk_id string.

    Uses UUID5 with a fixed namespace so the same chunk_id
    always maps to the same UUID. This enables idempotent
    upserts.

    Parameters
    ----------
    chunk_id : str
        The chunk identifier.

    Returns
    -------
    str
        UUID string.
    """

    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    return str(uuid.uuid5(namespace, chunk_id))


# ==========================================================
# Load Embedded Chunks
# ==========================================================

def load_all_embeddings() -> list[dict]:
    """
    Load all embedded chunks from JSONL files in data/embeddings/.

    Returns
    -------
    list[dict]
        List of dicts, each containing metadata, text,
        and embedding vector.
    """

    jsonl_files = sorted(EMBEDDING_DIR.rglob("*.jsonl"))

    logger.info("Found %d embedding JSONL files.", len(jsonl_files))

    all_items: list[dict] = []

    for jsonl_path in jsonl_files:
        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_items.append(json.loads(line))

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Error reading %s: %s",
                jsonl_path.name,
                str(e),
            )

    logger.info("Loaded %d embedded chunks.", len(all_items))

    return all_items


# ==========================================================
# Build Qdrant Points
# ==========================================================

def build_point(item: dict) -> PointStruct:
    """
    Convert an embedded chunk dict into a Qdrant PointStruct.

    Parameters
    ----------
    item : dict
        Chunk dict with embedding vector and metadata.

    Returns
    -------
    PointStruct
        Qdrant point ready for upsert.
    """

    chunk_id = item.get("chunk_id", "unknown")

    point = PointStruct(
        id=chunk_id_to_uuid(chunk_id),
        vector=item["embedding"],
        payload={
            "title": item.get("document_title", ""),
            "category": item.get("category", "Other"),
            "topics": item.get("topics", []),
            "source": item.get("source_file", ""),
            "chunk_id": chunk_id,
            "section": item.get("section_heading", ""),
            "text": item.get("text", ""),
        },
    )

    return point


# ==========================================================
# Upload All Points
# ==========================================================

def upload_all_points(
    client: QdrantClient,
    items: list[dict],
) -> dict:
    """
    Build Qdrant points from embedded chunks and upsert
    them in batches.

    Parameters
    ----------
    client : QdrantClient
        Connected Qdrant client.
    items : list[dict]
        List of embedded chunk dicts.

    Returns
    -------
    dict
        Upload statistics.
    """

    stats = {
        "total_items": len(items),
        "uploaded": 0,
        "failed_batches": 0,
    }

    # Build all points
    points: list[PointStruct] = []

    for item in items:
        try:
            point = build_point(item)
            points.append(point)
        except Exception as e:
            logger.warning(
                "Cannot build point for %s: %s",
                item.get("chunk_id", "?"),
                str(e),
            )

    logger.info("Built %d Qdrant points.", len(points))

    # Upsert in batches
    for batch_start in tqdm(
        range(0, len(points), UPSERT_BATCH_SIZE),
        desc="Uploading to Qdrant",
    ):
        batch = points[batch_start : batch_start + UPSERT_BATCH_SIZE]

        try:
            client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=batch,
            )

            stats["uploaded"] += len(batch)

        except Exception as e:
            logger.error(
                "Batch upsert failed (batch %d-%d): %s",
                batch_start,
                batch_start + len(batch),
                str(e),
            )
            stats["failed_batches"] += 1

    return stats


# ==========================================================
# Collection Stats
# ==========================================================

def log_collection_stats(client: QdrantClient) -> None:
    """Log the current collection statistics from Qdrant."""

    try:
        info = client.get_collection(QDRANT_COLLECTION)

        logger.info("=" * 60)
        logger.info("QDRANT COLLECTION STATS")
        logger.info("=" * 60)
        logger.info("Collection        : %s", QDRANT_COLLECTION)
        logger.info("Points Count      : %s", info.points_count)
        logger.info("Vectors Count     : %s", info.vectors_count)
        logger.info("Status            : %s", info.status)
        logger.info("=" * 60)

    except Exception as e:
        logger.warning("Cannot fetch collection stats: %s", str(e))


# ==========================================================
# Print Summary
# ==========================================================

def print_summary(stats: dict) -> None:
    """Log a formatted upload summary."""

    logger.info("=" * 60)
    logger.info("QDRANT UPLOAD COMPLETE")
    logger.info("=" * 60)
    logger.info("Total Items       : %d", stats["total_items"])
    logger.info("Uploaded          : %d", stats["uploaded"])
    logger.info("Failed Batches    : %d", stats["failed_batches"])
    logger.info("=" * 60)


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """Entry point for the Qdrant upload pipeline stage."""

    logger.info("=" * 60)
    logger.info("Qdrant Uploader Started")
    logger.info("=" * 60)

    start_time = time.perf_counter()

    # Connect to Qdrant
    client = create_qdrant_client()

    # Ensure collection exists
    ensure_collection(client)

    # Load embeddings
    items = load_all_embeddings()

    if not items:
        logger.warning("No embeddings found. Run generate_embeddings.py first.")
        return

    # Upload
    stats = upload_all_points(client, items)

    elapsed = round(time.perf_counter() - start_time, 1)
    logger.info("Total upload time: %.1fs", elapsed)

    # Show stats
    print_summary(stats)
    log_collection_stats(client)


if __name__ == "__main__":
    main()
