
"""
config.py

Central configuration for the University RAG Knowledge Pipeline.
Modify this file only when adding new universities, changing folders,
or updating crawler settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================================
# ENVIRONMENT
# ==========================================================

load_dotenv()

# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parent

# ==========================================================
# WEBSITE CONFIGURATION
# ==========================================================

WEBSITES = [
    {
        "name": "NUST",
        "url": "https://nust.edu.pk/downloads/"
    },
    {
        "name": "MCS",
        "url": "https://mcs.nust.edu.pk/downloads/"
    }
]

# ==========================================================
# DIRECTORIES
# ==========================================================

DATA_DIR = PROJECT_ROOT / "data"

RAW_DIR = DATA_DIR / "raw"

NUST_DIR = RAW_DIR / "NUST"

MCS_DIR = RAW_DIR / "MCS"

EXTRACTED_DIR = DATA_DIR / "extracted"

METADATA_DIR = DATA_DIR / "metadata"

CHUNK_DIR = DATA_DIR / "chunked"

EMBEDDING_DIR = DATA_DIR / "embeddings"

LOG_DIR = PROJECT_ROOT / "logs"

# Create directories automatically
for directory in [
    DATA_DIR,
    RAW_DIR,
    NUST_DIR,
    MCS_DIR,
    EXTRACTED_DIR,
    METADATA_DIR,
    CHUNK_DIR,
    EMBEDDING_DIR,
    LOG_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

# ==========================================================
# OUTPUT FILES
# ==========================================================

DOCUMENT_INDEX = DATA_DIR / "document_index.csv"

DISCOVERED_LINKS = DATA_DIR / "visited_links.txt"

# ==========================================================
# REQUEST SETTINGS
# ==========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20

# ==========================================================
# CRAWLER SETTINGS
# ==========================================================

MAX_DEPTH = 2

MAX_WORKERS = 8

ALLOWED_DOMAINS = [
    "nust.edu.pk",
    "mcs.nust.edu.pk"
]

# ==========================================================
# FILE TYPES
# ==========================================================

ALLOWED_EXTENSIONS = [
    ".pdf"
]

# ==========================================================
# LOGGING
# ==========================================================

LOG_FILE = LOG_DIR / "crawler.log"

ANALYSER_LOG = LOG_DIR / "ai_analyser.log"

CHUNKER_LOG = LOG_DIR / "chunker.log"

EMBEDDING_LOG = LOG_DIR / "embeddings.log"

QDRANT_LOG = LOG_DIR / "qdrant_upload.log"

TEST_LOG = LOG_DIR / "test_pipeline.log"

# ==========================================================
# PDF FILTER KEYWORDS
# ==========================================================

INCLUDE_KEYWORDS = [
    "student",
    "handbook",
    "prospectus",
    "hostel",
    "orientation",
    "fee",
    "academic",
    "calendar",
    "policy",
    "guide",
    "admission",
    "undergraduate",
    "graduate",
    "financial",
    "aid",
    "library",
    "department"
]

EXCLUDE_KEYWORDS = [
    "tender",
    "quotation",
    "vendor",
    "procurement",
    "employee",
    "hr",
    "recruitment",
    "auction",
    "corrigendum"
]

# ==========================================================
# MISTRAL AI SETTINGS
# ==========================================================
# NOTE: This project originally targeted OpenAI (gpt-4.1-mini +
# text-embedding-3-small). The OpenAI key in .env was found to be
# invalid (401 Unauthorized) with no working fallback, so the
# pipeline now runs entirely on Mistral AI, which was verified
# working for chat, structured JSON output, and embeddings.

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# ==========================================================
# OPENAI SETTINGS (voice only — Whisper transcription + TTS)
# ==========================================================
# Mistral has no speech-to-text/text-to-speech API, so the backend's
# /api/transcribe and /api/tts routes use OpenAI specifically for
# these two features. The rest of the app (chat, embeddings) is
# unaffected and stays on Mistral.

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Chat model used for document analysis (utils/llm.py).
# Override via MISTRAL_MODEL in .env if a different model is desired.
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

# Embedding model used for chunk + query embeddings.
EMBEDDING_MODEL = "mistral-embed"

EMBEDDING_DIMENSIONS = 1024

# Pricing per 1M tokens (USD). Verified 2026-07 at
# https://mistral.ai/pricing/api/ — update if Mistral changes pricing.
PRICING = {
    "mistral-small-latest": {
        "input": 0.15,
        "output": 0.60,
    },
    "mistral-large-latest": {
        "input": 0.50,
        "output": 1.50,
    },
    "mistral-embed": {
        "input": 0.10,
        "output": 0.0,
    },
}

# ==========================================================
# CHUNKING SETTINGS
# ==========================================================

MAX_CHUNK_TOKENS = 800          # Target max tokens per chunk
MIN_CHUNK_TOKENS = 100          # Minimum viable chunk size
CHUNK_OVERLAP_TOKENS = 100      # Overlap between consecutive chunks

# ==========================================================
# EMBEDDING SETTINGS
# ==========================================================

# Mistral's embeddings endpoint has a lower practical batch limit than
# OpenAI's. embed_texts() auto-splits on HTTP 400 regardless, but starting
# smaller avoids needless failed-then-retried requests.
EMBEDDING_BATCH_SIZE = 32       # Max texts per embedding API call

# ==========================================================
# QDRANT SETTINGS
# ==========================================================

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

QDRANT_COLLECTION = "nust_knowledge"

# ==========================================================
# DATABASE SETTINGS (backend chat history — PostgreSQL)
# ==========================================================
# Local dev previously used a SQLite file (backend/db/chat.db), which
# doesn't survive redeploys on most hosting platforms. The backend now
# requires a real Postgres connection string here — e.g. the one Neon
# gives you when you create a project (postgresql://user:pass@host/db).

DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================================================
# CORS SETTINGS (backend)
# ==========================================================
# Comma-separated list of origins allowed to call the API. Defaults to
# the local Vite dev server; set to the deployed frontend URL(s) (e.g.
# https://your-app.vercel.app) in production.

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# ==========================================================
# FIREBASE AUTH SETTINGS (backend token verification)
# ==========================================================
# The frontend signs users in directly with Firebase (Google or
# email/password) and sends the resulting ID token on every request.
# The backend verifies that token with the Firebase Admin SDK, which
# needs a service account credential. Provide EITHER the JSON content
# directly (handy for Railway/host env vars — paste the downloaded
# service account file's content compacted to one line) OR a path to
# the JSON file on disk (handy for local dev).

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")

FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

# ==========================================================
# ALLOWED CATEGORIES (shared across pipeline)
# ==========================================================

ALLOWED_CATEGORIES = [
    "Admissions",
    "Academics",
    "Hostel",
    "Examinations",
    "Fee Structure",
    "Financial Aid",
    "Library",
    "Campus Facilities",
    "Departments",
    "Student Services",
    "Orientation",
    "Campus Life",
    "Policies",
    "Forms",
    "Administration",
    "Other",
]
