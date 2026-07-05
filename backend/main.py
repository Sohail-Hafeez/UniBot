"""
backend/main.py

FastAPI entrypoint for the NUST/MCS student assistant backend.
The route/service modules import each other as bare top-level packages
(e.g. `from routes.chat import ...`), which only resolve with backend/
itself as the working directory — run it from inside backend/:

    cd backend
    uvicorn main:app --reload --port 8000

(config.py and utils/ from the ingestion pipeline, one level up, are
still reachable via the sys.path insert below regardless of cwd.)
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# config.py lives at the project root, one level above backend/. Make it
# importable regardless of the working directory uvicorn is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALLOWED_ORIGINS  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    from routes.chat import episodic
    await episodic.init_db()
    yield
    await episodic.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


from routes.chat import router  # noqa: E402
from routes.voice import router as voice_router  # noqa: E402
app.include_router(router)
app.include_router(voice_router)
