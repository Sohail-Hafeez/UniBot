"""
06_test_pipeline.py

End-to-end retrieval test for the RAG pipeline.

Embeds a test query, searches Qdrant for the top-k most
similar chunks, and displays results with similarity scores.

No LLM generation — pure vector retrieval test.

Author: Sohail
"""

import logging
import sys
import time

# Windows consoles default to cp1252, which can't encode the box-drawing
# characters used below. Force UTF-8 so results render everywhere.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from qdrant_client import QdrantClient

from config import (
    MISTRAL_API_KEY,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
    TEST_LOG,
)
from utils.llm import embed_texts

# ==========================================================
# Logging
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(TEST_LOG, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ==========================================================
# Test Queries
# ==========================================================

TEST_QUERIES = [
    "What is hostel fee?",
    "How do I apply for admission?",
    "What scholarships are available?",
    "What is the dress code policy?",
    "How to register for courses?",
]

TOP_K = 5  # Number of results to retrieve per query


# ==========================================================
# Embed Query
# ==========================================================

def embed_query(query: str) -> list[float]:
    """
    Generate an embedding vector for a query string.

    Parameters
    ----------
    query : str
        The search query text.

    Returns
    -------
    list[float]
        The embedding vector (1024 dimensions for mistral-embed).
    """

    embeddings, _ = embed_texts([query])

    return embeddings[0]


# ==========================================================
# Search Qdrant
# ==========================================================

def search_qdrant(
    client: QdrantClient,
    query_vector: list[float],
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Search Qdrant for the most similar chunks.

    Parameters
    ----------
    client : QdrantClient
        Connected Qdrant client.
    query_vector : list[float]
        The query embedding vector.
    top_k : int
        Number of results to return.

    Returns
    -------
    list[dict]
        List of result dicts with score and payload.
    """

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    )

    formatted_results: list[dict] = []

    for point in results.points:

        formatted_results.append({
            "score": round(point.score, 4),
            "chunk_id": point.payload.get("chunk_id", ""),
            "title": point.payload.get("title", ""),
            "category": point.payload.get("category", ""),
            "section": point.payload.get("section", ""),
            "source": point.payload.get("source", ""),
            "topics": point.payload.get("topics", []),
            "text": point.payload.get("text", ""),
        })

    return formatted_results


# ==========================================================
# Display Results
# ==========================================================

def display_results(query: str, results: list[dict]) -> None:
    """
    Print formatted retrieval results to console and log.

    Parameters
    ----------
    query : str
        The original query.
    results : list[dict]
        List of retrieval results.
    """

    separator = "=" * 70

    print(f"\n{separator}")
    print(f"  QUERY: {query}")
    print(separator)

    if not results:
        print("  No results found.\n")
        logger.warning("No results for query: %s", query)
        return

    for i, result in enumerate(results, 1):

        score = result["score"]
        chunk_id = result["chunk_id"]
        title = result["title"]
        category = result["category"]
        section = result["section"]
        source = result["source"]
        text = result["text"]

        # Truncate text for display
        display_text = text[:500]

        if len(text) > 500:
            display_text += "..."

        print(f"\n  ┌─ Result #{i}")
        print(f"  │ Similarity : {score:.4f}")
        print(f"  │ Chunk ID   : {chunk_id}")
        print(f"  │ Title      : {title}")
        print(f"  │ Category   : {category}")
        print(f"  │ Section    : {section}")
        print(f"  │ Source     : {source}")
        print(f"  │")
        print(f"  │ Text Preview:")

        # Indent the text preview
        for line in display_text.split("\n"):
            print(f"  │   {line}")

        print(f"  └{'─' * 50}")

    print()

    # Log summary
    logger.info(
        "Query: '%s' → %d results (top score: %.4f)",
        query,
        len(results),
        results[0]["score"] if results else 0.0,
    )


# ==========================================================
# Run Single Query Test
# ==========================================================

def test_single_query(
    qdrant_client: QdrantClient,
    query: str,
) -> list[dict]:
    """
    Run a complete retrieval test for a single query.

    Parameters
    ----------
    qdrant_client : QdrantClient
        Connected Qdrant client.
    query : str
        The test query.

    Returns
    -------
    list[dict]
        Retrieval results.
    """

    logger.info("Testing query: '%s'", query)

    # Step 1: Embed the query
    start = time.perf_counter()

    query_vector = embed_query(query)

    embed_time = round(time.perf_counter() - start, 3)
    logger.info("Query embedded in %.3fs", embed_time)

    # Step 2: Search Qdrant
    start = time.perf_counter()

    results = search_qdrant(qdrant_client, query_vector)

    search_time = round(time.perf_counter() - start, 3)
    logger.info("Qdrant search in %.3fs (%d results)", search_time, len(results))

    # Step 3: Display
    display_results(query, results)

    return results


# ==========================================================
# Main
# ==========================================================

def main() -> None:
    """
    Entry point for the end-to-end retrieval test.

    Runs all test queries and displays results.
    """

    logger.info("=" * 60)
    logger.info("RAG Pipeline End-to-End Test")
    logger.info("=" * 60)

    # Validate API key
    if not MISTRAL_API_KEY:
        logger.error("MISTRAL_API_KEY not set in .env")
        return

    # Connect to Qdrant
    logger.info("Connecting to Qdrant at %s", QDRANT_URL)

    kwargs = {"url": QDRANT_URL, "timeout": 30}

    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY

    try:
        qdrant_client = QdrantClient(**kwargs)

        # Verify collection exists
        info = qdrant_client.get_collection(QDRANT_COLLECTION)

        logger.info(
            "Collection '%s' has %d points.",
            QDRANT_COLLECTION,
            info.points_count,
        )

    except Exception as e:
        logger.error("Cannot connect to Qdrant: %s", str(e))
        print(
            "\n  ERROR: Cannot connect to Qdrant.\n"
            f"  URL: {QDRANT_URL}\n"
            f"  Collection: {QDRANT_COLLECTION}\n"
            f"  Error: {e}\n"
            "\n  Make sure Qdrant is running and the collection exists.\n"
            "  Run qdrant_upload.py first.\n"
        )
        return

    # Run test queries
    start_time = time.perf_counter()

    all_results = {}

    for query in TEST_QUERIES:
        results = test_single_query(qdrant_client, query)
        all_results[query] = results

    total_time = round(time.perf_counter() - start_time, 1)

    # Final summary
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)
    print(f"  Queries Tested  : {len(TEST_QUERIES)}")
    print(f"  Total Time      : {total_time}s")
    print(f"  Collection      : {QDRANT_COLLECTION}")
    print(f"  Points in DB    : {info.points_count}")

    for query, results in all_results.items():
        top_score = results[0]["score"] if results else 0.0
        print(f"  • '{query}' → top score: {top_score:.4f}")

    print("=" * 70)
    print()

    logger.info("All tests completed in %.1fs", total_time)


if __name__ == "__main__":
    main()
