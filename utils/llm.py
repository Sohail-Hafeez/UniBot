"""
utils/llm.py

Production-grade Mistral AI utility for the RAG pipeline.

This is the single gateway module for all LLM and embedding calls in the
pipeline. Every other stage (analysis, embedding generation, retrieval
testing) imports from here instead of talking to the Mistral SDK directly,
so retry policy, timeouts, logging, and cost tracking stay consistent.

Features:
    - Reusable singleton Mistral client
    - Exponential backoff retries (via tenacity) on transient failures only
      (timeouts, connection errors, 429/5xx) — auth/validation errors fail fast
    - Timeout handling
    - Token usage tracking
    - Execution time logging
    - Cost estimation
    - Structured JSON output via Mistral's json_schema response format
    - Robust fallback JSON parsing + automatic retry on invalid JSON
    - Batch text embeddings with automatic batch-splitting on oversized
      requests
    - Comprehensive error handling

Usage:
    from utils.llm import ask_llm, ask_llm_json, embed_texts

    # Plain text response
    text = ask_llm("Summarize this document: ...")

    # Structured JSON response with a Pydantic schema
    result = ask_llm_json(
        prompt="Analyse this document...",
        schema=MyPydanticModel,
    )
    # result["response"] -> dict
    # result["usage"]    -> token counts
    # result["cost"]     -> estimated cost in USD
    # result["time"]     -> execution time in seconds

    # Embeddings
    vectors, total_tokens = embed_texts(["text one", "text two"])
"""

import json
import logging
import re
import time
from typing import Any, Optional, Type

import httpx
from mistralai.client import Mistral
from mistralai.client.errors import SDKError
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from config import EMBEDDING_MODEL, MISTRAL_API_KEY, MISTRAL_MODEL, PRICING

# ==========================================================
# Logger
# ==========================================================

logger = logging.getLogger(__name__)

# ==========================================================
# Client Singleton
# ==========================================================

_client: Optional[Mistral] = None

# Request timeout, in milliseconds, applied to every API call.
_REQUEST_TIMEOUT_MS = 60_000


def _get_client() -> Mistral:
    """
    Returns a lazily-initialised Mistral client.

    Raises immediately if the API key is missing so failures surface at
    startup rather than after burning through a batch of documents.
    """
    global _client

    if _client is not None:
        return _client

    if not MISTRAL_API_KEY:
        raise ValueError(
            "MISTRAL_API_KEY not found. Set it in your .env file."
        )

    _client = Mistral(api_key=MISTRAL_API_KEY, timeout_ms=_REQUEST_TIMEOUT_MS)

    logger.info("Mistral client initialised.")

    return _client


# ==========================================================
# Retry Predicate
# ==========================================================

# HTTP status codes worth retrying: timeouts, rate limits, server errors.
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _is_retryable_error(exc: BaseException) -> bool:
    """
    Decide whether an exception from the Mistral SDK is transient and
    therefore worth retrying.

    Retries on network-level failures (timeouts, connection drops) and
    on HTTP responses with a retryable status code. Everything else
    (bad API key, invalid request, malformed schema, etc.) fails fast
    since retrying would never succeed.

    Parameters
    ----------
    exc : BaseException
        The exception raised by the SDK call.

    Returns
    -------
    bool
        True if the call should be retried.
    """

    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True

    if isinstance(exc, SDKError):
        status_code = getattr(exc.raw_response, "status_code", None)
        return status_code in _RETRYABLE_STATUS_CODES

    return False


# ==========================================================
# Cost Estimation
# ==========================================================

def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Estimate the API call cost in USD based on token counts.

    Parameters
    ----------
    model : str
        The model name (must exist in PRICING).
    input_tokens : int
        Number of input (prompt) tokens.
    output_tokens : int
        Number of output (completion) tokens.

    Returns
    -------
    float
        Estimated cost in USD.
    """

    pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return round(input_cost + output_cost, 8)


# ==========================================================
# Pydantic → JSON Schema Converter
# ==========================================================

def _pydantic_to_json_schema(model: Type[BaseModel]) -> dict:
    """
    Convert a Pydantic model class to a JSON schema dict suitable for
    Mistral's `json_schema` structured output mode.

    The schema is wrapped with additionalProperties: false and all
    properties are marked as required, matching Mistral's strict mode
    requirements (same shape as OpenAI's structured outputs).
    """

    schema = model.model_json_schema()

    schema["additionalProperties"] = False

    if "properties" in schema:
        schema["required"] = list(schema["properties"].keys())

    for key in ["title", "$defs"]:
        schema.pop(key, None)

    return schema


# ==========================================================
# Fallback JSON Extraction
# ==========================================================

def _extract_json_from_text(text: str) -> Optional[dict]:
    """
    Attempt to extract JSON from a text string that might contain
    markdown code fences, extra whitespace, or surrounding prose.

    Tries in order:
        1. Direct json.loads
        2. Strip markdown code fences (```json ... ```)
        3. Regex/brace-matching extraction of the first JSON object

    Returns None if all methods fail.
    """

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 2: Strip markdown code fences
    cleaned = text.strip()

    fence_pattern = r"^```(?:json)?\s*\n?(.*?)\n?\s*```$"

    match = re.search(fence_pattern, cleaned, re.DOTALL)

    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # Strategy 3: Find first { ... } block via brace matching
    start = cleaned.find("{")

    if start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start : i + 1])
                except (json.JSONDecodeError, TypeError):
                    break

    return None


# ==========================================================
# Chat Message Content Normalisation
# ==========================================================

def normalise_content(content: Any) -> str:
    """
    Normalise a Mistral assistant message's `content` field to plain text.

    `content` is usually a plain string, but the SDK types allow a list
    of content chunks (e.g. for multimodal responses). This flattens
    either shape into a single string.

    Parameters
    ----------
    content : Any
        The raw `message.content` value from a chat completion response.

    Returns
    -------
    str
        Flattened text content.
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for chunk in content:
            text = getattr(chunk, "text", None)
            if text is None and isinstance(chunk, dict):
                text = chunk.get("text")
            if text:
                parts.append(text)
        return "".join(parts)

    return str(content)


# ==========================================================
# Core Chat Call (with retries)
# ==========================================================

@retry(
    retry=retry_if_exception(_is_retryable_error),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _call_llm(
    prompt: str,
    model: str,
    temperature: float,
    json_schema: Optional[dict] = None,
    schema_name: str = "structured_output",
) -> dict:
    """
    Internal function that makes the actual Mistral chat completion call.

    Wrapped with tenacity retry for transient failures.

    Parameters
    ----------
    prompt : str
        The user prompt.
    model : str
        Model identifier.
    temperature : float
        Sampling temperature.
    json_schema : dict, optional
        If provided, enables structured JSON output mode.
    schema_name : str
        Name for the JSON schema (used by the Mistral API).

    Returns
    -------
    dict
        Raw result with keys: "text", "input_tokens", "output_tokens".
    """

    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }

    if json_schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": json_schema,
                "strict": True,
            },
        }

    response = client.chat.complete(**kwargs)

    text = normalise_content(response.choices[0].message.content)

    usage = response.usage
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    return {
        "text": text.strip(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


# ==========================================================
# Public API: ask_llm()
# ==========================================================

def ask_llm(
    prompt: str,
    temperature: float = 0.0,
    model: str = MISTRAL_MODEL,
) -> str:
    """
    Send a prompt to Mistral and return the plain text response.

    Parameters
    ----------
    prompt : str
        The user prompt to send.
    temperature : float
        Sampling temperature (0.0 = deterministic).
    model : str
        The model to use.

    Returns
    -------
    str
        The model's text response.

    Raises
    ------
    Exception
        If all retry attempts are exhausted.
    """

    start = time.perf_counter()

    result = _call_llm(
        prompt=prompt,
        model=model,
        temperature=temperature,
    )

    elapsed = round(time.perf_counter() - start, 2)

    cost = estimate_cost(model, result["input_tokens"], result["output_tokens"])

    logger.info(
        "ask_llm | model=%s | in=%d out=%d | cost=$%.6f | time=%.2fs",
        model,
        result["input_tokens"],
        result["output_tokens"],
        cost,
        elapsed,
    )

    return result["text"]


# ==========================================================
# Public API: ask_llm_json()
# ==========================================================

MAX_JSON_RETRIES = 3


def ask_llm_json(
    prompt: str,
    schema: Type[BaseModel],
    temperature: float = 0.0,
    model: str = MISTRAL_MODEL,
) -> dict:
    """
    Send a prompt and return a structured JSON response.

    Uses Mistral's `json_schema` structured output mode with a
    Pydantic-derived JSON schema, so the model is constrained to emit
    exactly the requested structure. Falls back to robust manual JSON
    extraction (handles stray markdown fences / prose) and retries on
    failure.

    Parameters
    ----------
    prompt : str
        The user prompt to send.
    schema : Type[BaseModel]
        A Pydantic model class defining the expected JSON structure.
    temperature : float
        Sampling temperature (0.0 = deterministic).
    model : str
        The model to use.

    Returns
    -------
    dict
        Keys:
            - "response": The parsed JSON as a Python dict.
            - "usage": {"input_tokens": int, "output_tokens": int}
            - "cost": Estimated cost in USD.
            - "time": Execution time in seconds.

    Raises
    ------
    ValueError
        If valid JSON cannot be extracted after all retries.
    """

    json_schema = _pydantic_to_json_schema(schema)
    schema_name = schema.__name__

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_JSON_RETRIES + 1):

        start = time.perf_counter()

        try:
            result = _call_llm(
                prompt=prompt,
                model=model,
                temperature=temperature,
                json_schema=json_schema,
                schema_name=schema_name,
            )
        except Exception as e:
            logger.error(
                "ask_llm_json | API call failed on attempt %d/%d: %s",
                attempt,
                MAX_JSON_RETRIES,
                str(e),
            )
            last_error = e
            continue

        elapsed = round(time.perf_counter() - start, 2)

        cost = estimate_cost(
            model, result["input_tokens"], result["output_tokens"]
        )

        parsed = _extract_json_from_text(result["text"])

        if parsed is not None:

            logger.info(
                "ask_llm_json | model=%s | in=%d out=%d | "
                "cost=$%.6f | time=%.2fs | attempt=%d",
                model,
                result["input_tokens"],
                result["output_tokens"],
                cost,
                elapsed,
                attempt,
            )

            return {
                "response": parsed,
                "usage": {
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                },
                "cost": cost,
                "time": elapsed,
            }

        logger.warning(
            "ask_llm_json | Invalid JSON on attempt %d/%d. "
            "Raw text (first 200 chars): %s",
            attempt,
            MAX_JSON_RETRIES,
            result["text"][:200],
        )

        last_error = ValueError(
            f"Could not parse JSON from response: {result['text'][:200]}"
        )

    raise ValueError(
        f"Failed to extract valid JSON after {MAX_JSON_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


# ==========================================================
# Core Embedding Call (with retries)
# ==========================================================

@retry(
    retry=retry_if_exception(_is_retryable_error),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _embed_batch(texts: list[str], model: str) -> tuple[list[list[float]], int]:
    """
    Generate embeddings for a batch of texts in a single API call.

    Wrapped with tenacity retry for transient failures.

    Parameters
    ----------
    texts : list[str]
        List of text strings to embed. Must be non-empty.
    model : str
        Embedding model identifier.

    Returns
    -------
    tuple[list[list[float]], int]
        (list of embedding vectors, total tokens used)
    """

    client = _get_client()

    response = client.embeddings.create(model=model, inputs=texts)

    embeddings = [item.embedding for item in response.data]

    total_tokens = getattr(response.usage, "total_tokens", 0) or 0

    return embeddings, total_tokens


# ==========================================================
# Public API: embed_texts()
# ==========================================================

def embed_texts(
    texts: list[str],
    model: str = EMBEDDING_MODEL,
) -> tuple[list[list[float]], int]:
    """
    Embed a batch of texts, automatically splitting the batch in half
    and retrying if the API rejects it as too large (HTTP 400).

    This avoids needing to hard-code an exact, undocumented batch-size
    limit — the function degrades gracefully instead of failing outright.

    Parameters
    ----------
    texts : list[str]
        Texts to embed.
    model : str
        Embedding model identifier.

    Returns
    -------
    tuple[list[list[float]], int]
        (list of embedding vectors in the same order as `texts`,
        total tokens consumed across all sub-batches)

    Raises
    ------
    Exception
        If embedding fails for reasons other than an oversized batch,
        or a single text cannot be embedded on its own.
    """

    if not texts:
        return [], 0

    start = time.perf_counter()

    try:
        embeddings, tokens = _embed_batch(texts, model)

        elapsed = round(time.perf_counter() - start, 2)
        cost = estimate_cost(model, tokens, 0)

        logger.info(
            "embed_texts | model=%s | count=%d | tokens=%d | "
            "cost=$%.6f | time=%.2fs",
            model,
            len(texts),
            tokens,
            cost,
            elapsed,
        )

        return embeddings, tokens

    except SDKError as e:
        status_code = getattr(e.raw_response, "status_code", None)

        if status_code == 400 and len(texts) > 1:
            logger.warning(
                "embed_texts | Batch of %d rejected (HTTP 400). "
                "Splitting and retrying.",
                len(texts),
            )

            mid = len(texts) // 2
            left_emb, left_tokens = embed_texts(texts[:mid], model)
            right_emb, right_tokens = embed_texts(texts[mid:], model)

            return left_emb + right_emb, left_tokens + right_tokens

        raise
