"""
backend/services/firebase_auth.py

Firebase ID token verification for the FastAPI backend.

The frontend signs users in directly with Firebase (Google or
email/password) and attaches the resulting ID token as
`Authorization: Bearer <token>` on every request. This module verifies
that token server-side with the Firebase Admin SDK so route handlers
know exactly which user is calling — the client-supplied session_id
is never trusted as proof of identity on its own.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import (  # noqa: E402
    FIREBASE_PROJECT_ID,
    FIREBASE_SERVICE_ACCOUNT_JSON,
    FIREBASE_SERVICE_ACCOUNT_PATH,
)

logger = logging.getLogger(__name__)

_app: Optional[firebase_admin.App] = None


def _get_app() -> firebase_admin.App:
    """
    Lazily-initialised Firebase Admin app (shared singleton).

    Reads credentials from FIREBASE_SERVICE_ACCOUNT_JSON (inline JSON,
    preferred for hosted deployments) or FIREBASE_SERVICE_ACCOUNT_PATH
    (a file path, convenient for local dev).

    Raises
    ------
    RuntimeError
        If neither credential source is configured, or the JSON is
        malformed.
    """

    global _app

    if _app is not None:
        return _app

    if FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON. Paste the "
                "full downloaded service-account file content, compacted "
                "to a single line."
            ) from e
        cred = credentials.Certificate(service_account_info)
    elif FIREBASE_SERVICE_ACCOUNT_PATH:
        cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    else:
        raise RuntimeError(
            "Firebase is not configured. Set FIREBASE_SERVICE_ACCOUNT_JSON "
            "or FIREBASE_SERVICE_ACCOUNT_PATH in .env."
        )

    options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID else None
    _app = firebase_admin.initialize_app(cred, options=options)

    logger.info("Firebase Admin initialised (project=%s).", FIREBASE_PROJECT_ID)

    return _app


class CurrentUser:
    """The authenticated caller, extracted from a verified Firebase ID token."""

    def __init__(self, uid: str, email: Optional[str], name: Optional[str]):
        self.uid = uid
        self.email = email
        self.name = name


async def get_current_user(
    authorization: str = Header(..., description="Bearer <Firebase ID token>"),
) -> CurrentUser:
    """
    FastAPI dependency: verifies the Firebase ID token on the request and
    returns the caller's identity.

    The frontend already gates the whole app behind an "email verified"
    check for a clean UX, but that's client-side only — anyone with a
    valid-but-unverified token could otherwise call the API directly. This
    is the actual enforcement: an email/password account that never
    confirmed the email it was created with cannot reach any endpoint
    that depends on this dependency, full stop.

    Raises
    ------
    HTTPException
        401 if the header is missing/malformed or the token is invalid,
        expired, or revoked. 403 if the token is valid but the account's
        email has not been verified.
    """

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
        )

    token = authorization[len("Bearer "):].strip()

    try:
        _get_app()
    except RuntimeError as e:
        # Server misconfiguration (no credentials set yet) is not the
        # caller's fault — surface it distinctly from a bad/expired token.
        logger.error("Firebase Admin not configured: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e

    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as e:
        logger.warning("Firebase token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from e

    if not decoded.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="EMAIL_NOT_VERIFIED",
        )

    return CurrentUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        name=decoded.get("name"),
    )
