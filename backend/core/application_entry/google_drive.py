from __future__ import annotations

import io
import os
from functools import lru_cache

GOOGLE_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"


def is_configured() -> bool:
    credentials_file = (os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE") or "").strip()
    client_id = (os.getenv("GOOGLE_DRIVE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_DRIVE_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN") or "").strip()
    root_folder_id = (os.getenv("GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID") or "").strip()
    has_service_account = bool(credentials_file)
    has_user_oauth = bool(client_id and client_secret and refresh_token)
    return bool(root_folder_id and (has_user_oauth or has_service_account))


@lru_cache(maxsize=1)
def _drive_service():
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials as UserCredentials
    from googleapiclient.discovery import build

    client_id = (os.getenv("GOOGLE_DRIVE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_DRIVE_CLIENT_SECRET") or "").strip()
    refresh_token = (os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN") or "").strip()
    credentials_file = (os.getenv("GOOGLE_DRIVE_CREDENTIALS_FILE") or "").strip()

    if client_id and client_secret and refresh_token:
        credentials = UserCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=GOOGLE_OAUTH_TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=GOOGLE_DRIVE_SCOPES,
        )
        credentials.refresh(Request())
    elif credentials_file:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=GOOGLE_DRIVE_SCOPES,
        )
    else:
        raise RuntimeError(
            "Google Drive is not configured. Set either GOOGLE_DRIVE_CLIENT_ID / "
            "GOOGLE_DRIVE_CLIENT_SECRET / GOOGLE_DRIVE_REFRESH_TOKEN or "
            "GOOGLE_DRIVE_CREDENTIALS_FILE."
        )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _root_folder_id() -> str:
    folder_id = (os.getenv("GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID") or "").strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_APPLICATIONS_FOLDER_ID is not configured.")
    return folder_id


def _folder_label(application_type: str) -> str:
    value = str(application_type or "").strip().casefold()
    if value == "district":
        return "district"
    if value == "public":
        return "public"
    if value == "institution":
        return "institution"
    return "others"


@lru_cache(maxsize=8)
def _ensure_child_folder(folder_name: str) -> str:
    service = _drive_service()
    parent_id = _root_folder_id()
    escaped_name = folder_name.replace("'", "\\'")
    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{escaped_name}' "
        f"and '{parent_id}' in parents "
        "and trashed = false"
    )
    result = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name)",
            pageSize=1,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = result.get("files") or []
    if files:
        return str(files[0].get("id") or "").strip()
    created = (
        service.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return str(created.get("id") or "").strip()


def upload_application_attachment(
    *,
    content: bytes,
    display_name: str,
    content_type: str,
    application_type: str,
    application_reference: str,
) -> dict[str, object]:
    from googleapiclient.http import MediaIoBaseUpload

    service = _drive_service()
    target_folder_id = _ensure_child_folder(_folder_label(application_type))
    file_metadata = {
        "name": display_name,
        "parents": [target_folder_id],
        "description": f"{application_type}:{application_reference}",
    }
    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype=content_type or "application/octet-stream",
        resumable=False,
    )
    created = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id,name,mimeType,size,webViewLink,webContentLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {
        "file_id": str(created.get("id") or "").strip(),
        "mime_type": str(created.get("mimeType") or content_type or "application/octet-stream").strip(),
        "view_url": str(created.get("webViewLink") or created.get("webContentLink") or "").strip(),
        "size": int(created.get("size") or 0),
    }


def list_application_attachments(*, application_type: str, application_reference: str) -> list[dict[str, object]]:
    service = _drive_service()
    target_folder_id = _ensure_child_folder(_folder_label(application_type))
    reference_prefix = f"{(application_reference or '').strip()}_"
    query = f"'{target_folder_id}' in parents and trashed = false"
    if reference_prefix:
        escaped_prefix = reference_prefix.replace("'", "\\'")
        query += f" and name contains '{escaped_prefix}'"
    result = (
        service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id,name,mimeType,size,webViewLink,webContentLink,createdTime)",
            pageSize=100,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    matched_files = []
    prefix_lower = reference_prefix.casefold()
    for entry in result.get("files") or []:
        name = str(entry.get("name") or "").strip()
        if prefix_lower and not name.casefold().startswith(prefix_lower):
            continue
        matched_files.append(
            {
                "file_id": str(entry.get("id") or "").strip(),
                "file_name": name,
                "mime_type": str(entry.get("mimeType") or "").strip(),
                "view_url": str(entry.get("webViewLink") or entry.get("webContentLink") or "").strip(),
                "size": int(entry.get("size") or 0),
                "created_time": str(entry.get("createdTime") or "").strip(),
            }
        )
    matched_files.sort(key=lambda item: (str(item.get("created_time") or ""), str(item.get("file_name") or "")), reverse=True)
    return matched_files


def download_file(file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    service = _drive_service()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.getvalue()


def get_file_metadata(file_id: str) -> dict[str, object]:
    service = _drive_service()
    data = (
        service.files()
        .get(
            fileId=file_id,
            fields="id,name,mimeType,webViewLink,webContentLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {
        "file_id": str(data.get("id") or "").strip(),
        "file_name": str(data.get("name") or "").strip(),
        "mime_type": str(data.get("mimeType") or "").strip(),
        "view_url": str(data.get("webViewLink") or data.get("webContentLink") or "").strip(),
    }


def rename_file(file_id: str, new_name: str) -> dict[str, object]:
    service = _drive_service()
    data = (
        service.files()
        .update(
            fileId=file_id,
            body={"name": new_name},
            fields="id,name,mimeType,webViewLink,webContentLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {
        "file_id": str(data.get("id") or "").strip(),
        "file_name": str(data.get("name") or "").strip(),
        "mime_type": str(data.get("mimeType") or "").strip(),
        "view_url": str(data.get("webViewLink") or data.get("webContentLink") or "").strip(),
    }


def delete_file(file_id: str) -> None:
    service = _drive_service()
    service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
