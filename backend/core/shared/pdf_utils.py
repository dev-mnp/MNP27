from __future__ import annotations

"""Shared PDF and image helpers used across multiple modules."""

import io
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph

try:
    from PIL import Image as PILImage
except Exception:  # pragma: no cover - optional dependency fallback
    PILImage = None


def _indian_grouping(number_text: str) -> str:
    if len(number_text) <= 3:
        return number_text
    last_three = number_text[-3:]
    remaining = number_text[:-3]
    groups = []
    while len(remaining) > 2:
        groups.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.insert(0, remaining)
    return ",".join(groups + [last_three])


def _pdf_currency(value) -> str:
    amount = Decimal(str(value or 0))
    sign = "-" if amount < 0 else ""
    amount = abs(amount).quantize(Decimal("0.01"))
    whole, fraction = f"{amount:.2f}".split(".", 1)
    return f"{sign}{_indian_grouping(whole)}.{fraction}"


def _pdf_logo_path() -> str | None:
    logo_path = Path(__file__).resolve().parents[1] / "static" / "core" / "images" / "pdf-logo.png"
    return str(logo_path) if logo_path.exists() else None


def _pdf_guru_logo_path() -> str | None:
    guru_logo_path = Path(__file__).resolve().parents[1] / "static" / "core" / "images" / "guru-logo.jpg"
    return str(guru_logo_path) if guru_logo_path.exists() else None


def _pdf_signature_path() -> str | None:
    signature_path = Path(__file__).resolve().parents[1] / "static" / "core" / "images" / "pdf-sign.jpg"
    return str(signature_path) if signature_path.exists() else None


def _fitted_pdf_image(path: str | None, *, max_width_mm: float, max_height_mm: float):
    if not path:
        return Paragraph("", getSampleStyleSheet()["BodyText"])
    try:
        width_px, height_px = ImageReader(path).getSize()
        if not width_px or not height_px:
            raise ValueError("invalid image size")
        scale = min((max_width_mm * mm) / width_px, (max_height_mm * mm) / height_px)
        return Image(path, width=width_px * scale, height=height_px * scale)
    except Exception:
        return Paragraph("", getSampleStyleSheet()["BodyText"])


def _fitted_pdf_image_source(source, *, max_width_mm: float, max_height_mm: float):
    if not source:
        return Paragraph("", getSampleStyleSheet()["BodyText"])
    stream = None
    image_source = source
    try:
        if isinstance(source, (bytes, bytearray)):
            stream = io.BytesIO(source)
            image_source = stream
        width_px, height_px = ImageReader(image_source).getSize()
        if not width_px or not height_px:
            raise ValueError("invalid image size")
        scale = min((max_width_mm * mm) / width_px, (max_height_mm * mm) / height_px)
        if stream is not None:
            stream.seek(0)
            image_source = stream
        return Image(image_source, width=width_px * scale, height=height_px * scale)
    except Exception:
        return Paragraph("", getSampleStyleSheet()["BodyText"])


def _optimized_report_logo(source, mime_type: str | None = None, *, max_width_px: int = 420, max_height_px: int = 520):
    if not source:
        return source, mime_type or "image/png"
    if PILImage is None:
        return source, mime_type or "image/png"
    try:
        raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
        image = PILImage.open(io.BytesIO(raw))
        image.load()
        resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS", getattr(PILImage, "LANCZOS", 1))
        image.thumbnail((max_width_px, max_height_px), resampling)
        has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        buffer = io.BytesIO()
        if has_alpha:
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue(), "image/png"
        image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
        return buffer.getvalue(), "image/jpeg"
    except Exception:
        return source, mime_type or "image/png"


def extract_pdf_form_fields(pdf_bytes: bytes) -> list[dict]:
    if not pdf_bytes:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return []
    fields: list[dict] = []
    seen = set()
    for page_index, page in enumerate(reader.pages, start=1):
        for annot_ref in page.get("/Annots") or []:
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue
            if annot.get("/Subtype") != "/Widget":
                continue
            field_name = str(annot.get("/T") or "").strip()
            if not field_name or field_name in seen:
                continue
            rect = annot.get("/Rect") or []
            fields.append(
                {
                    "name": field_name,
                    "page": page_index,
                    "rect": [float(coord) for coord in rect[:4]] if rect else [],
                }
            )
            seen.add(field_name)
    if fields:
        return fields
    try:
        field_map = reader.get_fields() or {}
    except Exception:
        field_map = {}
    for field_name in field_map.keys():
        if field_name in seen:
            continue
        fields.append({"name": str(field_name), "page": 1, "rect": []})
        seen.add(field_name)
    return fields


def fill_pdf_form_from_rows(
    template_pdf_bytes: bytes,
    rows: list[dict],
    field_map: dict[str, str],
    *,
    derived_aid_value_key: str = "__derived_aid_value__",
) -> io.BytesIO:
    if not template_pdf_bytes:
        raise ValueError("Upload a PDF template first.")
    if not rows:
        raise ValueError("No rows are available to fill.")
    if not field_map:
        raise ValueError("Map at least one PDF field before downloading.")

    def _row_lookup(row: dict, key: str):
        if key in row:
            return row.get(key)
        normalized = str(key or "").strip().casefold()
        for row_key, value in row.items():
            if str(row_key or "").strip().casefold() == normalized:
                return value
        return ""

    def _resolved_value(row: dict, mapped_key: str) -> str:
        mapping = str(mapped_key or "").strip()
        if not mapping or mapping == "__blank__":
            return ""
        if mapping == derived_aid_value_key:
            item_type = str(_row_lookup(row, "Item Type") or "").strip().casefold()
            if item_type == "aid":
                return str(_row_lookup(row, "Total Value") or _row_lookup(row, "total_value") or "").strip()
            return ""
        value = _row_lookup(row, mapping)
        return "" if value is None else str(value)

    merged_writer = PdfWriter()
    for row in rows:
        row_reader = PdfReader(io.BytesIO(template_pdf_bytes))
        row_writer = PdfWriter()
        row_writer.append(row_reader)
        row_writer.set_need_appearances_writer()
        fill_values = {
            field_name: _resolved_value(row, mapped_key)
            for field_name, mapped_key in field_map.items()
            if str(mapped_key or "").strip()
        }
        if fill_values:
            row_writer.update_page_form_field_values(row_writer.pages[0], fill_values)
        page_buffer = io.BytesIO()
        row_writer.write(page_buffer)
        page_buffer.seek(0)
        merged_writer.append(PdfReader(page_buffer))
    merged_writer.set_need_appearances_writer()
    output = io.BytesIO()
    merged_writer.write(output)
    output.seek(0)
    return output


def _normalized_docx_report_logo(source, mime_type: str | None = None, *, canvas_width_px: int = 300, canvas_height_px: int = 300):
    if not source:
        return None, "image/png"
    if PILImage is None:
        return source, mime_type or "image/png"
    try:
        raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
        image = PILImage.open(io.BytesIO(raw))
        image.load()
        resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS", getattr(PILImage, "LANCZOS", 1))
        image = image.convert("RGBA")
        image.thumbnail((canvas_width_px, canvas_height_px), resampling)
        canvas_image = PILImage.new("RGBA", (canvas_width_px, canvas_height_px), (255, 255, 255, 0))
        offset_x = max((canvas_width_px - image.width) // 2, 0)
        offset_y = max((canvas_height_px - image.height) // 2, 0)
        canvas_image.paste(image, (offset_x, offset_y), image)
        buffer = io.BytesIO()
        canvas_image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), "image/png"
    except Exception:
        return source, mime_type or "image/png"
