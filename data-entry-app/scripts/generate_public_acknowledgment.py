#!/usr/bin/env python3
"""
Generate public acknowledgment PDFs by filling a fillable PDF template.

Implements the notebook workflow:
1) Read Generated Token file, filter Beneficiary Type == Public.
2) Read public details file, filter QUANTITY != 0, keep App/Aadhar/Name/Address/Mobile.
3) Merge datasets on App No + Name.
4) Fill missing Aadhar/Mobile/Address defaults.
5) Fill per-beneficiary PDF and merge to all_acknowledgment.pdf.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from pypdf import PdfMerger, PdfReader, PdfWriter
except Exception:
    print("ERROR: pypdf is required. Install with: python3 -m pip install pypdf", file=sys.stderr)
    raise


DEFAULT_FIELD_MAP = {
    "address": "Address",
    "bf name": "Name",
    "App no": "App. No.",
    "token": "Start Token No.",
    "mobile": "Mobile",
    "Aadhar": "Aadhar",
    "article": "Article Name",
}


@dataclass
class Record:
    data: Dict[str, Any]

    def get(self, key: str, default: Any = "") -> Any:
        return self.data.get(key, default)


def normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", str(header).strip().lower())


def split_app_name(name_val: str) -> tuple[str, str]:
    raw = str(name_val or "").strip()
    if " - " in raw:
        app, name = raw.split(" - ", 1)
        return app.strip(), name.strip()
    return "", raw


def read_table(path: Path) -> List[Record]:
    ext = path.suffix.lower()
    if ext == ".csv":
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [Record(dict(row)) for row in reader]

    if ext in {".xlsx", ".xls"}:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "pandas is required for Excel inputs. Install with: python3 -m pip install pandas openpyxl"
            ) from exc
        df = pd.read_excel(path)
        return [Record(row.to_dict()) for _, row in df.iterrows()]

    raise ValueError(f"Unsupported file type: {path}")


def pick_col(row: Record, candidates: Iterable[str]) -> Optional[str]:
    norm_map = {normalize_header(k): k for k in row.data.keys()}
    for c in candidates:
        key = norm_map.get(normalize_header(c))
        if key:
            return key
    return None


def to_number(val: Any) -> float:
    text = str(val or "").replace(",", "").strip()
    if text == "":
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def build_public_generated_records(generated_rows: List[Record]) -> List[Record]:
    out: List[Record] = []
    for row in generated_rows:
        btype_key = pick_col(row, ["Beneficiary Type"])
        if not btype_key:
            continue
        btype = str(row.get(btype_key, "")).strip().lower()
        if btype != "public":
            continue

        app_key = pick_col(row, ["Application Number", "App. No.", "App No"])
        name_key = pick_col(row, ["Name", "Name of Beneficiary", "Beneficiary Name"])
        article_key = pick_col(row, ["Article Name", "Item", "Requested Item"])
        token_start_key = pick_col(row, ["Start Token No.", "Token Start No."])

        full_name = str(row.get(name_key or "", "")).strip()
        app_from_name, name_from_name = split_app_name(full_name)
        app_no = str(row.get(app_key or "", "")).strip() or app_from_name
        pure_name = name_from_name if name_from_name else full_name

        rec = dict(row.data)
        rec["App. No."] = app_no
        rec["Name"] = pure_name
        rec["Article Name"] = str(row.get(article_key or "", "")).strip()
        rec["Start Token No."] = int(to_number(row.get(token_start_key or "", 0)))
        out.append(Record(rec))

    return out


def build_public_details_map(public_rows: List[Record]) -> Dict[tuple[str, str], Record]:
    mapped: Dict[tuple[str, str], Record] = {}
    for row in public_rows:
        qty_key = pick_col(row, ["QUANTITY", "Quantity"])
        if qty_key and to_number(row.get(qty_key, 0)) == 0:
            continue

        app_key = pick_col(row, ["App. No.", "Application Number", "App No"])
        name_key = pick_col(row, ["Name", "Beneficiary Name"])
        aadhar_key = pick_col(row, ["Aadhar (Without Space)", "Aadhar", "Aadhaar"])
        address_key = pick_col(row, ["Address"])
        mobile_key = pick_col(row, ["Mobile", "Mobile No"])

        app_no = str(row.get(app_key or "", "")).strip()
        name = str(row.get(name_key or "", "")).strip()
        if not app_no or not name:
            continue

        rec = dict(row.data)
        rec["Aadhar"] = str(row.get(aadhar_key or "", "")).strip()
        rec["Address"] = str(row.get(address_key or "", "")).strip()
        rec["Mobile"] = str(row.get(mobile_key or "", "")).strip()
        mapped[(app_no, name)] = Record(rec)

    return mapped


def merge_records(generated_public: List[Record], details_map: Dict[tuple[str, str], Record]) -> List[Record]:
    merged: List[Record] = []
    for row in generated_public:
        app_no = str(row.get("App. No.", "")).strip()
        name = str(row.get("Name", "")).strip()
        details = details_map.get((app_no, name))
        rec = dict(row.data)
        if details:
            rec["Aadhar"] = details.get("Aadhar", "")
            rec["Address"] = details.get("Address", "")
            rec["Mobile"] = details.get("Mobile", "")
        else:
            rec["Aadhar"] = ""
            rec["Address"] = ""
            rec["Mobile"] = ""
        merged.append(Record(rec))

    merged.sort(key=lambda r: str(r.get("Article Name", "")).lower())
    return merged


def normalize_defaults(records: List[Record]) -> List[Record]:
    normalized: List[Record] = []
    for row in records:
        rec = dict(row.data)
        rec["Aadhar"] = str(rec.get("Aadhar") or "0")
        rec["Mobile"] = str(rec.get("Mobile") or "0")
        rec["Address"] = str(rec.get("Address") or "Add")
        normalized.append(Record(rec))
    return normalized


def get_template_fields(template_path: Path) -> Dict[str, Any]:
    reader = PdfReader(str(template_path))
    fields = reader.get_fields() or {}
    return fields


def fill_template_once(template_path: Path, output_path: Path, values: Dict[str, Any]) -> None:
    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    if reader.pages:
        writer.update_page_form_field_values(writer.pages[0], values, auto_regenerate=False)
    writer.set_need_appearances_writer()
    with output_path.open("wb") as f:
        writer.write(f)


def write_debug_csv(rows: List[Record], path: Path) -> None:
    if not rows:
        return
    headers = list(rows[0].data.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate public acknowledgment PDFs from token + public details.")
    parser.add_argument("--generated", required=True, help="Path to Generated Token file (csv/xlsx).")
    parser.add_argument("--public-data", required=True, help="Path to Public Data file (csv/xlsx).")
    parser.add_argument("--template", required=True, help="Path to fillable acknowledgment PDF template.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument(
        "--field-map-json",
        default="",
        help="Optional JSON file mapping PDF field name -> source column name.",
    )
    parser.add_argument(
        "--merged-name",
        default="all_acknowledgment.pdf",
        help="Output merged PDF file name.",
    )
    parser.add_argument(
        "--keep-individual",
        action="store_true",
        help="Keep individual filled PDFs (default deletes them after merge).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    generated_path = Path(args.generated).expanduser().resolve()
    public_data_path = Path(args.public_data).expanduser().resolve()
    template_path = Path(args.template).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not generated_path.exists():
        print(f"ERROR: generated file not found: {generated_path}", file=sys.stderr)
        return 1
    if not public_data_path.exists():
        print(f"ERROR: public data file not found: {public_data_path}", file=sys.stderr)
        return 1
    if not template_path.exists():
        print(f"ERROR: template PDF not found: {template_path}", file=sys.stderr)
        return 1

    fields = get_template_fields(template_path)
    if not fields:
        print(
            "ERROR: template PDF has no fillable fields (AcroForm missing). "
            "Use your editable 'acknowledgment stage_2.pdf' template.",
            file=sys.stderr,
        )
        return 2

    field_map = dict(DEFAULT_FIELD_MAP)
    if args.field_map_json:
        field_map_path = Path(args.field_map_json).expanduser().resolve()
        with field_map_path.open("r", encoding="utf-8") as f:
            field_map = json.load(f)

    generated_rows = read_table(generated_path)
    public_rows = read_table(public_data_path)

    generated_public = build_public_generated_records(generated_rows)
    details_map = build_public_details_map(public_rows)
    merged = normalize_defaults(merge_records(generated_public, details_map))

    debug_csv_path = output_dir / "Beneficiary_list.csv"
    write_debug_csv(merged, debug_csv_path)

    temp_dir = output_dir / "_filled_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    filled_paths: List[Path] = []
    for row in merged:
        token_no = int(to_number(row.get("Start Token No.", 0)))
        if token_no <= 0:
            continue
        fill_values: Dict[str, Any] = {}
        for pdf_field, source_col in field_map.items():
            fill_values[pdf_field] = str(row.get(source_col, ""))

        out_pdf = temp_dir / f"{token_no}_filled.pdf"
        fill_template_once(template_path, out_pdf, fill_values)
        filled_paths.append(out_pdf)

    if not filled_paths:
        print("WARNING: no fillable public rows found to generate acknowledgment PDFs.")
        return 0

    merged_pdf_path = output_dir / args.merged_name
    merger = PdfMerger()
    for path in sorted(filled_paths, key=lambda p: int(re.findall(r"\d+", p.stem)[0])):
        merger.append(str(path))
    with merged_pdf_path.open("wb") as f:
        merger.write(f)
    merger.close()

    if not args.keep_individual:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"Generated: {merged_pdf_path}")
    print(f"Rows merged/debug CSV: {debug_csv_path}")
    print(f"Template field count: {len(fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

