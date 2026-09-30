"""Build a Drive API v3 service from a service-account or OAuth JSON (optional dependency).

    pip install google-api-python-client google-auth
Credentials path: env MARKFLOW_GOOGLE_CREDENTIALS (never in git). The doc must be shared with the
service account's e-mail (Viewer or Commenter is enough).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class CredentialsMissing(RuntimeError):
    pass


def credentials_path() -> Path | None:
    value = os.environ.get("MARKFLOW_GOOGLE_CREDENTIALS")
    return Path(value) if value and Path(value).is_file() else None


def build_drive_service(path: Path | None = None):
    path = path or credentials_path()
    if path is None:
        raise CredentialsMissing("set MARKFLOW_GOOGLE_CREDENTIALS to the Google credentials JSON")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise CredentialsMissing("pip install google-api-python-client google-auth") from exc
    info = json.loads(Path(path).read_text(encoding="utf-8"))
    if info.get("type") != "service_account":
        raise CredentialsMissing(f"{path}: only service-account JSON is supported for now")
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)
