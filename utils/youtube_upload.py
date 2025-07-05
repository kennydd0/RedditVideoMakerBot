from __future__ import annotations

import os # os.path will be replaced by pathlib
from pathlib import Path # Added for pathlib
import logging # Added for logging
from typing import List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = Path("youtube_client_secrets.json") # Use Path
TOKEN_FILE = Path("youtube_token.json") # Use Path

logger = logging.getLogger(__name__)

def _get_service():
    """Return an authenticated YouTube service object."""
    creds: Optional[Credentials] = None
    logger.debug(f"Looking for existing token file at: {TOKEN_FILE}")
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            logger.info(f"Loaded credentials from {TOKEN_FILE}")
        except Exception as e:
            logger.warning(f"Failed to load credentials from {TOKEN_FILE}: {e}. Will attempt re-authentication.")
            creds = None # Ensure creds is None if loading failed

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Credentials expired. Attempting to refresh token...")
            try:
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully.")
            except Exception as e:
                logger.error(f"Failed to refresh credentials: {e}. Will attempt re-authentication.", exc_info=True)
                creds = None # Force re-authentication

        if not creds or not creds.valid: # Check again if refresh failed or was not attempted
            logger.info("No valid credentials found or refresh failed. Starting new OAuth2 flow...")
            if not CLIENT_SECRETS_FILE.exists():
                logger.error(f"Client secrets file '{CLIENT_SECRETS_FILE}' not found. Cannot authenticate.")
                raise FileNotFoundError(f"YouTube client secrets file '{CLIENT_SECRETS_FILE}' is required for authentication.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
                # run_console will print to stdout and read from stdin.
                logger.info("Please follow the instructions in your browser to authenticate.")
                creds = flow.run_console()
                logger.info("OAuth2 flow completed. Credentials obtained.")
            except Exception as e:
                logger.error(f"OAuth2 flow failed: {e}", exc_info=True)
                raise RuntimeError(f"Failed to obtain YouTube credentials via OAuth2 flow: {e}")

        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as token_file_handle:
                token_file_handle.write(creds.to_json())
            logger.info(f"Credentials saved to {TOKEN_FILE}")
        except IOError as e:
            logger.error(f"Failed to save token file to {TOKEN_FILE}: {e}", exc_info=True)
            # Not raising here as the service might still work with in-memory creds for this session.

    logger.debug("Returning YouTube service object.")
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    filepath: str,
    title: str,
    description: str = "",
    *,
    privacy_status: str = "private",
    tags: Optional[List[str]] = None,
) -> dict:
    """Upload a video to YouTube with the given metadata."""
    youtube = _get_service()
    body = {
        "snippet": {"title": title, "description": description, "tags": tags or []},
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(filepath)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    return request.execute()

