"""YouTube upload service using the YouTube Data API v3 with OAuth2."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# YouTube category IDs
CATEGORIES = {
    "film": "1",
    "autos": "2",
    "music": "10",
    "pets": "15",
    "sports": "17",
    "gaming": "20",
    "vlog": "21",
    "people": "22",
    "comedy": "23",
    "entertainment": "24",
    "news": "25",
    "howto": "26",
    "education": "27",
    "science": "28",
    "nonprofits": "29",
}

TOKEN_FILE = Path.home() / ".ytauto" / "youtube_token.json"
CLIENT_SECRETS_FILE = Path.home() / ".ytauto" / "client_secrets.json"

# OAuth2 scopes required
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_authenticated_service():
    """Build and return an authenticated YouTube API service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                raise FileNotFoundError(
                    f"YouTube client secrets not found at {CLIENT_SECRETS_FILE}\n\n"
                    "To set up YouTube upload:\n"
                    "1. Go to https://console.cloud.google.com/apis/credentials\n"
                    "2. Create an OAuth 2.0 Client ID (Desktop application)\n"
                    "3. Download the JSON file\n"
                    "4. Save it as ~/.ytauto/client_secrets.json\n"
                    "5. Run 'ytauto upload <job-id>' again"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=8090, open_browser=True)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "22",
    privacy: str = "private",
    thumbnail_path: Path | None = None,
) -> dict:
    """Upload a video to YouTube.

    Returns a dict with: video_id, url, title, status.
    """
    from googleapiclient.http import MediaFileUpload

    youtube = _get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    result = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": response["snippet"]["title"],
        "status": response["status"]["privacyStatus"],
    }

    # Upload thumbnail if provided
    if thumbnail_path and thumbnail_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
            ).execute()
            result["thumbnail_set"] = True
        except Exception as exc:
            logger.warning("Failed to set thumbnail: %s", exc)
            result["thumbnail_set"] = False

    return result
