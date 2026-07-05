"""
backend/services/rag.py

Retrieval-augmented chat service for the NUST/MCS student assistant.

Wires together the same Mistral + Qdrant stack used by the ingestion
pipeline (config.py, utils/llm.py) with an async Mistral client for
low-latency streaming chat inside FastAPI's event loop.
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from mistralai.client import Mistral
from qdrant_client import AsyncQdrantClient

# The ingestion pipeline (config.py, utils/llm.py) lives at the project
# root, one level above backend/. Make it importable regardless of the
# working directory uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import (  # noqa: E402
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)
from utils.llm import ask_llm, embed_texts, normalise_content  # noqa: E402

TOP_K = 5

SYSTEM_PROMPT_TEMPLATE = """You are the official AI assistant for NUST (National University of Sciences and Technology) and its MCS (Military College of Signals) department, built to help newly admitted students.

You answer questions about: admissions, hostel, fee structure, scholarships, registration, academics, departments, student services, campus life, rules and regulations, orientation, library, transport, and clubs.

Rules:
- Answer ONLY using the context provided below. Do not invent facts, numbers, or policies that aren't in it.
- If the context doesn't contain the answer, say so honestly and suggest the student contact the relevant NUST/MCS office — do not guess.
- Be concise, warm, and clear. You're often talking to a nervous new student.
- Format with markdown (lists, bold) when it aids clarity.

CONTEXT:
{context}
"""

_mistral_client: Optional[Mistral] = None
_qdrant_client: Optional[AsyncQdrantClient] = None


def _get_mistral_client() -> Mistral:
    """Lazily-initialised async-capable Mistral client (shared singleton)."""
    global _mistral_client
    if _mistral_client is None:
        if not MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY not found. Set it in your .env file.")
        _mistral_client = Mistral(api_key=MISTRAL_API_KEY, timeout_ms=60_000)
    return _mistral_client


def _get_qdrant_client() -> AsyncQdrantClient:
    """Lazily-initialised async Qdrant client (shared singleton)."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30
        )
    return _qdrant_client


async def retrieve_context(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Embed the user's message and retrieve the top-k most relevant
    knowledge-base chunks from Qdrant.

    Parameters
    ----------
    query : str
        The student's question.
    top_k : int
        Number of chunks to retrieve.

    Returns
    -------
    list[dict]
        Chunks with score, title, category, section, source, text.
    """

    # embed_texts is sync (shared with the ingestion pipeline) — run off
    # the event loop thread so it doesn't block other requests.
    embeddings, _ = await asyncio.to_thread(embed_texts, [query])
    if not embeddings:
        return []

    client = _get_qdrant_client()
    results = await client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=embeddings[0],
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "score": round(point.score, 4),
            "title": point.payload.get("title", ""),
            "category": point.payload.get("category", ""),
            "section": point.payload.get("section", ""),
            "source": point.payload.get("source", ""),
            "text": point.payload.get("text", ""),
        }
        for point in results.points
    ]


def build_system_prompt(chunks: list[dict]) -> str:
    """Build the RAG system prompt from retrieved context chunks."""

    if not chunks:
        context = "No relevant documents were found for this question."
    else:
        blocks = []
        for i, chunk in enumerate(chunks, 1):
            header = f"[{i}] {chunk['title']}"
            if chunk.get("section"):
                header += f" — {chunk['section']}"
            blocks.append(f"{header}\n{chunk['text']}")
        context = "\n\n---\n\n".join(blocks)

    return SYSTEM_PROMPT_TEMPLATE.format(context=context)


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """
    Stream a chat completion token-by-token from Mistral.

    Parameters
    ----------
    messages : list[dict]
        Full message history, including the RAG system prompt.

    Yields
    ------
    str
        Successive text tokens as they arrive.
    """

    client = _get_mistral_client()
    stream = await client.chat.stream_async(model=MISTRAL_MODEL, messages=messages)

    async for event in stream:
        delta = event.data.choices[0].delta
        token = normalise_content(delta.content)
        if token:
            yield token


async def summarize(messages: list[dict]) -> str:
    """Summarise older conversation turns in 3-5 sentences (used by short-term memory)."""

    formatted = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in messages)
    prompt = (
        "Summarize the following conversation in 3-5 sentences. "
        "Preserve key facts, decisions, and context.\n\n" + formatted
    )
    return await asyncio.to_thread(ask_llm, prompt, 0.3)


async def generate_title(messages: list[dict]) -> str:
    """Generate a short (<=5 word) title for a new conversation."""

    formatted = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in messages[:4])
    prompt = (
        "Give this conversation a title in 5 words or fewer. "
        "Return only the title, no punctuation.\n\n" + formatted
    )
    title = await asyncio.to_thread(ask_llm, prompt, 0.3)
    return title.strip().strip('"')
