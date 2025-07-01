from __future__ import annotations

import os
from typing import List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = "youtube_client_secrets.json"
TOKEN_FILE = "youtube_token.json"


def _get_service():
    """Return an authenticated YouTube service object."""
    creds: Optional[Credentials] = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_console()
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
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

