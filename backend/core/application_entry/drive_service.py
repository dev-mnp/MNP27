from __future__ import annotations

import mimetypes
from dataclasses import dataclass

from core.application_entry import google_drive


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES_PER_APPLICATION = 2
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp", "doc", "docx", "xls", "xlsx", "csv"}


class DriveServiceError(Exception):
    pass


@dataclass(frozen=True)
class DriveUploadResult:
    file_id: str
    mime_type: str
    view_url: str


def is_configured() -> bool:
    return google_drive.is_configured()


def root_folder_info() -> dict[str, str]:
    return google_drive.root_folder_info()


def child_folder_info(application_type: str) -> dict[str, str]:
    return google_drive.child_folder_info(application_type)


def ensure_upload_allowed(filename: str, size: int) -> None:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ext.upper() for ext in ALLOWED_EXTENSIONS))
        raise DriveServiceError(f"Unsupported file type. Allowed types: {allowed}.")
    if size > MAX_FILE_SIZE:
        raise DriveServiceError("File size must be 10 MB or less.")


def upload_attachment(*, application_type: str, reference: str, filename: str, content: bytes, content_type: str = "") -> DriveUploadResult:
    guessed_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    data = google_drive.upload_application_attachment(
        content=content,
        display_name=filename,
        content_type=guessed_type,
        application_type=application_type,
        application_reference=reference,
    )
    file_id = str(data.get("file_id") or "").strip()
    if not file_id:
        raise DriveServiceError("Google Drive upload did not return a file id.")
    return DriveUploadResult(
        file_id=file_id,
        mime_type=str(data.get("mime_type") or guessed_type).strip(),
        view_url=str(data.get("view_url") or "").strip(),
    )


def download_attachment(file_id: str) -> bytes:
    return google_drive.download_file(file_id)


def rename_attachment(file_id: str, filename: str) -> DriveUploadResult:
    data = google_drive.rename_file(file_id, filename)
    return DriveUploadResult(
        file_id=str(data.get("file_id") or "").strip(),
        mime_type=str(data.get("mime_type") or "").strip(),
        view_url=str(data.get("view_url") or "").strip(),
    )


def delete_attachment(file_id: str) -> None:
    google_drive.delete_file(file_id)


def attachment_exists(file_id: str) -> bool:
    google_drive.get_file_metadata(file_id)
    return True
