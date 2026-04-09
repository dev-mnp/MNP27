from __future__ import annotations

"""
Shared business logic for numbering, totals, PDF generation, and audit helpers.

When a rule should be reused by multiple views or serializers, it usually
belongs here instead of being duplicated inside ``views.py`` or ``web_views.py``.
"""

import io
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from django.utils import timezone
from django.utils.html import escape

from . import models


def next_fund_request_number() -> str:
    numbers = (
        models.FundRequest.objects.exclude(fund_request_number__isnull=True)
        .exclude(fund_request_number="")
        .values_list("fund_request_number", flat=True)
    )
    max_seq = 0
    for number in numbers:
        sequence = models.parse_fund_request_sequence(number)
        if sequence is None:
            continue
        max_seq = max(max_seq, sequence)
    return models.format_fund_request_number(f"FR-{max_seq + 1}")


def next_purchase_order_number() -> str:
    """
    Serial PO number format: MASM/MNPXXXYY
    Example for 2026: MASM/MNP00126
    """
    prefix = "MASM/MNP"
    year_suffix = timezone.localdate().strftime("%y")
    numbers = (
        models.PurchaseOrder.objects.exclude(purchase_order_number__isnull=True)
        .exclude(purchase_order_number="")
        .values_list("purchase_order_number", flat=True)
    )
    max_seq = 0
    for number in numbers:
        raw = str(number or "").strip().upper()
        if not raw.startswith(prefix):
            continue
        suffix = raw[len(prefix):]
        if len(suffix) != 5 or not suffix.isdigit():
            continue
        sequence_part = suffix[:3]
        year_part = suffix[3:]
        if year_part != year_suffix:
            continue
        max_seq = max(max_seq, int(sequence_part))
    return f"{prefix}{max_seq + 1:03d}{year_suffix}"


def ensure_purchase_order_number(purchase_order: models.PurchaseOrder) -> str:
    if purchase_order.purchase_order_number:
        return purchase_order.purchase_order_number
    purchase_order.purchase_order_number = next_purchase_order_number()
    purchase_order.save(update_fields=["purchase_order_number"])
    return purchase_order.purchase_order_number


def next_public_application_number() -> str:
    prefix = "P"
    latest = (
        models.PublicBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def next_institution_application_number() -> str:
    prefix = "I"
    latest = (
        models.InstitutionsBeneficiaryEntry.objects.filter(application_number__startswith=prefix)
        .order_by("-application_number")
        .values_list("application_number", flat=True)
        .first()
    )
    if not latest:
        return f"{prefix}001"
    try:
        seq = int(str(latest).replace(prefix, "", 1)) + 1
    except (TypeError, ValueError):
        seq = 1
    return f"{prefix}{seq:03d}"


def _find_matching_aid_article(aid_type: str | None):
    aid_label = str(aid_type or "").strip()
    queryset = models.Article.objects.filter(item_type=models.ItemTypeChoices.AID)
    if not aid_label:
        return queryset.order_by("article_name").first()

    exact = queryset.filter(article_name__iexact=aid_label).order_by("article_name").first()
    if exact:
        return exact
    exact = queryset.filter(category__iexact=aid_label).order_by("article_name").first()
    if exact:
        return exact
    partial = queryset.filter(article_name__icontains=aid_label).order_by("article_name").first()
    if partial:
        return partial
    partial = queryset.filter(category__icontains=aid_label).order_by("article_name").first()
    if partial:
        return partial
    return queryset.order_by("article_name").first()




def _resolve_fund_request_recipient_source(recipient: models.FundRequestRecipient):
    source_id = recipient.source_entry_id
    if not source_id or not recipient.beneficiary_type:
        return None
    if recipient.beneficiary_type == models.RecipientTypeChoices.DISTRICT:
        return models.DistrictBeneficiaryEntry.objects.select_related("article").filter(pk=source_id).first()
    if recipient.beneficiary_type == models.RecipientTypeChoices.PUBLIC:
        return models.PublicBeneficiaryEntry.objects.select_related("article").filter(pk=source_id).first()
    if recipient.beneficiary_type in {models.RecipientTypeChoices.INSTITUTIONS, models.RecipientTypeChoices.OTHERS}:
        return models.InstitutionsBeneficiaryEntry.objects.select_related("article").filter(pk=source_id).first()
    return None


def _aid_pdf_beneficiary_label(recipient: models.FundRequestRecipient) -> str:
    source_entry = _resolve_fund_request_recipient_source(recipient)
    beneficiary_type = recipient.beneficiary_type
    if beneficiary_type == models.RecipientTypeChoices.DISTRICT:
        if source_entry and getattr(source_entry, "district", None):
            return source_entry.district.district_name or "-"
        return recipient.district_name or recipient.recipient_name or "-"
    if beneficiary_type == models.RecipientTypeChoices.PUBLIC:
        if source_entry and getattr(source_entry, "application_number", None):
            return source_entry.application_number or "-"
        text = (recipient.beneficiary or "").strip()
        if text:
            return text.split(" - ", 1)[0].strip() or "-"
        return "-"
    if beneficiary_type in {models.RecipientTypeChoices.INSTITUTIONS, models.RecipientTypeChoices.OTHERS}:
        if source_entry and getattr(source_entry, "application_number", None):
            return source_entry.application_number or "-"
        text = (recipient.beneficiary or "").strip()
        if text:
            return text.split(" - ", 1)[0].strip() or "-"
        return "-"
    return recipient.recipient_name or "-"


def _article_pdf_beneficiary_label(item: models.FundRequestArticle) -> str:
    article = getattr(item, "article", None)
    if not article:
        return item.beneficiary or "-"

    labels = []
    if article.district_entries.exists():
        labels.append("District")
    if article.public_entries.exists():
        labels.append("Public")
    if article.institution_entries.exists():
        labels.append("Institution")

    if labels:
        return " & ".join(labels)

    stored = (item.beneficiary or "").strip()
    return stored or "-"

def sync_order_entries_from_fund_request(fund_request: models.FundRequest, actor: Optional[models.AppUser] = None) -> None:
    with transaction.atomic():
        models.OrderEntry.objects.filter(fund_request=fund_request).delete()

        if fund_request.status != models.FundRequestStatusChoices.SUBMITTED:
            return

        created_rows = []
        today = timezone.now().date()

        if fund_request.fund_request_type == models.FundRequestTypeChoices.ARTICLE:
            for line in fund_request.articles.select_related("article").all():
                quantity = max(int(line.quantity or 0), 0)
                if not line.article_id or quantity <= 0:
                    continue
                created_rows.append(
                    models.OrderEntry(
                        article=line.article,
                        quantity_ordered=quantity,
                        order_date=today,
                        status=models.OrderStatusChoices.ORDERED,
                        supplier_name=line.vendor_name or line.cheque_in_favour or fund_request.supplier_name or None,
                        unit_price=line.unit_price or 0,
                        notes=f"Created from Fund Request {fund_request.formatted_fund_request_number or 'Draft'}",
                        created_by=actor or fund_request.created_by,
                        fund_request=fund_request,
                    )
                )

        elif fund_request.fund_request_type == models.FundRequestTypeChoices.AID:
            fallback_article = _find_matching_aid_article(fund_request.aid_type)
            for recipient in fund_request.recipients.all():
                source_entry = _resolve_fund_request_recipient_source(recipient)
                article = getattr(source_entry, "article", None) or fallback_article
                quantity = int(getattr(source_entry, "quantity", 1) or 1)
                if not article or quantity <= 0:
                    continue
                amount = recipient.fund_requested or getattr(source_entry, "total_amount", 0) or 0
                recipient_name = recipient.recipient_name or recipient.name_of_beneficiary or recipient.name_of_institution or "Recipient"
                note_bits = [f"Created from Fund Request {fund_request.formatted_fund_request_number or 'Draft'}", recipient_name]
                if recipient.details:
                    note_bits.append(f"Details: {recipient.details}")
                if recipient.cheque_in_favour:
                    note_bits.append(f"Cheque / RTGS in Favour: {recipient.cheque_in_favour}")
                created_rows.append(
                    models.OrderEntry(
                        article=article,
                        quantity_ordered=quantity,
                        order_date=today,
                        status=models.OrderStatusChoices.ORDERED,
                        supplier_name=recipient.cheque_in_favour or None,
                        unit_price=amount,
                        notes=" - ".join(note_bits),
                        created_by=actor or fund_request.created_by,
                        fund_request=fund_request,
                    )
                )

        if created_rows:
            models.OrderEntry.objects.bulk_create(created_rows)


def _infer_aid_type_from_recipients(fund_request: models.FundRequest) -> str:
    for recipient in fund_request.recipients.all():
        text = str(recipient.beneficiary or '').strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split(' - ') if part.strip()]
        if len(parts) >= 2:
            return parts[1]
    return ''


def _ordinal(value: int) -> str:
    if 10 <= (value % 100) <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')
    return f'{value}{suffix}'


def _event_programme_title(event_year: int) -> str:
    birthday_number = max(event_year - 1940, 1)
    return (
        'Payment Request Details for MASM Makkal Nala Pani Programme on the eve of '
        f'{_ordinal(birthday_number)} Birthday Celebrations of His Holiness AMMA at '
        f'Melmaruvathur on 03-03-{event_year}'
    )


def _fund_request_title(fund_request: models.FundRequest) -> str:
    request_no = fund_request.formatted_fund_request_number or 'Draft'
    date_text = timezone.localtime(fund_request.created_at).strftime('%d-%m-%Y') if fund_request.created_at else timezone.localdate().strftime('%d-%m-%Y')
    if fund_request.fund_request_type == models.FundRequestTypeChoices.ARTICLE:
        suffix = 'Article'
    else:
        suffix = (fund_request.aid_type or _infer_aid_type_from_recipients(fund_request) or 'Aid').strip()
    return f'Fund Request No: {request_no}, Dated {date_text} - {suffix}'


def _fund_request_previous_cumulative(fund_request: models.FundRequest) -> Decimal:
    total = (
        models.FundRequest.objects.filter(
            status=models.FundRequestStatusChoices.SUBMITTED,
            created_at__lt=fund_request.created_at,
        )
        .exclude(pk=fund_request.pk)
        .aggregate(total=Sum('total_amount'))
        .get('total')
        or 0
    )
    return Decimal(str(total))


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
    logo_path = Path(__file__).resolve().parent / 'static' / 'core' / 'images' / 'pdf-logo.png'
    return str(logo_path) if logo_path.exists() else None


def _pdf_guru_logo_path() -> str | None:
    guru_logo_path = Path(__file__).resolve().parent / 'static' / 'core' / 'images' / 'guru-logo.jpg'
    return str(guru_logo_path) if guru_logo_path.exists() else None


def _pdf_signature_path() -> str | None:
    signature_path = Path(__file__).resolve().parent / 'static' / 'core' / 'images' / 'pdf-sign.jpg'
    return str(signature_path) if signature_path.exists() else None


def _fitted_pdf_image(path: str | None, *, max_width_mm: float, max_height_mm: float):
    if not path:
        return Paragraph('', getSampleStyleSheet()['BodyText'])
    try:
        width_px, height_px = ImageReader(path).getSize()
        if not width_px or not height_px:
            raise ValueError("invalid image size")
        scale = min((max_width_mm * mm) / width_px, (max_height_mm * mm) / height_px)
        return Image(path, width=width_px * scale, height=height_px * scale)
    except Exception:
        return Paragraph('', getSampleStyleSheet()['BodyText'])


def generate_fund_request_pdf(fund_request: models.FundRequest) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('mnp-normal', parent=styles['BodyText'], fontSize=8.5, leading=10)
    small = ParagraphStyle('mnp-small', parent=normal, fontSize=8.5, leading=10)
    header_title = ParagraphStyle(
        'mnp-header-title',
        parent=styles['Heading2'],
        alignment=1,
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        spaceAfter=3,
        textColor=colors.red,
    )
    header_sub = ParagraphStyle(
        'mnp-header-sub',
        parent=normal,
        alignment=1,
        fontName='Helvetica',
        fontSize=12,
        leading=14,
    )
    title_style = ParagraphStyle(
        'mnp-title',
        parent=styles['Heading3'],
        alignment=1,
        fontSize=15,
        leading=17,
        spaceBefore=6,
        fontName='Helvetica-Bold',
    )
    right_number = ParagraphStyle('mnp-right-number', parent=small, alignment=0, fontSize=8.5, leading=10)
    center_text = ParagraphStyle('mnp-center-text', parent=small, alignment=0, fontSize=8.5, leading=10)
    right_small = ParagraphStyle('mnp-right-small', parent=small, alignment=2, fontSize=8.5, leading=10)
    for_masm_style = ParagraphStyle('mnp-for-masm', parent=right_small, textColor=colors.HexColor('#166534'))
    totals_value_style = ParagraphStyle('mnp-totals-value', parent=small, alignment=2, fontSize=8.5, leading=10)

    story = []
    logo_path = _pdf_logo_path()
    guru_logo_path = _pdf_guru_logo_path()
    left_logo = _fitted_pdf_image(guru_logo_path, max_width_mm=15, max_height_mm=20)
    right_logo = _fitted_pdf_image(logo_path, max_width_mm=18, max_height_mm=24)
    event_year = timezone.localtime(fund_request.created_at).year if fund_request.created_at else timezone.localdate().year
    center_block = [
        Paragraph('OMSAKTHI', header_title),
        Paragraph(_event_programme_title(event_year), header_sub),
        Paragraph(_fund_request_title(fund_request), title_style),
    ]
    header = Table([[left_logo, center_block, right_logo]], colWidths=[24 * mm, 225 * mm, 24 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    story.extend([header, Spacer(1, 10)])

    header_bg = colors.HexColor('#e5e7eb')
    grid_color = colors.HexColor('#e5e7eb')

    if fund_request.fund_request_type == models.FundRequestTypeChoices.AID:
        rows = [[
            Paragraph('<b>SL No</b>', small),
            Paragraph('<b>Beneficiary</b>', small),
            Paragraph('<b>Name of beneficiary</b>', small),
            Paragraph('<b>Name of Institution</b>', small),
            Paragraph('<b>Details</b>', small),
            Paragraph('<b>Fund Requested</b>', small),
            Paragraph('<b>Aadhaar No</b>', small),
            Paragraph('<b>Cheque in Favour</b>', small),
            Paragraph('<b>Cheque No.</b>', small),
        ]]
        total = Decimal('0')
        for index, recipient in enumerate(fund_request.recipients.all(), start=1):
            amount = Decimal(str(recipient.fund_requested or 0))
            total += amount
            rows.append([
                Paragraph(str(index), small),
                Paragraph(_aid_pdf_beneficiary_label(recipient), small),
                Paragraph(recipient.name_of_beneficiary or recipient.recipient_name or '-', small),
                Paragraph(recipient.name_of_institution or '-', small),
                Paragraph(recipient.details or recipient.notes or '-', small),
                Paragraph(_pdf_currency(amount), right_number),
                Paragraph(recipient.aadhar_number or '-', small),
                Paragraph(recipient.cheque_in_favour or '-', small),
                Paragraph(recipient.cheque_no or '-', small),
            ])
        rows.append(['', '', '', '', Paragraph('<b>Total:</b>', small), Paragraph(f'<b>{_pdf_currency(total)}</b>', right_number), '', '', ''])
        col_widths = [12 * mm, 24 * mm, 35 * mm, 32 * mm, 26 * mm, 24 * mm, 28 * mm, 68 * mm, 24 * mm]
    else:
        rows = [[
            Paragraph('<b>SL No</b>', small),
            Paragraph('<b>Beneficiary</b>', small),
            Paragraph('<b>Article Name</b>', small),
            Paragraph('<b>GST No.</b>', small),
            Paragraph('<b>Qty</b>', small),
            Paragraph('<b>Price (Incl GST)</b>', small),
            Paragraph('<b>Value</b>', small),
            Paragraph('<b>Cheque in Favour</b>', small),
            Paragraph('<b>Cheque No.</b>', small),
        ]]
        total = Decimal('0')
        for index, item in enumerate(fund_request.articles.all(), start=1):
            value = Decimal(str(item.value or 0))
            total += value
            rows.append([
                Paragraph(str(item.sl_no or index), small),
                Paragraph(_article_pdf_beneficiary_label(item), small),
                Paragraph(item.article_name or '-', small),
                Paragraph(fund_request.gst_number or item.gst_no or '-', small),
                Paragraph(str(item.quantity or 0), center_text),
                Paragraph(_pdf_currency(item.price_including_gst or item.unit_price or 0), right_number),
                Paragraph(_pdf_currency(value), right_number),
                Paragraph(item.cheque_in_favour or '-', small),
                Paragraph(item.cheque_no or '-', small),
            ])
        rows.append(['', '', '', '', Paragraph('<b>Total:</b>', small), '', Paragraph(f'<b>{_pdf_currency(total)}</b>', right_number), '', ''])
        col_widths = [12 * mm, 24 * mm, 50 * mm, 24 * mm, 14 * mm, 24 * mm, 24 * mm, 77 * mm, 24 * mm]

    table = LongTable(rows, colWidths=col_widths, repeatRows=1, splitByRow=1)
    table.hAlign = 'LEFT'
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, grid_color),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    story.extend([table, Spacer(1, 12)])

    prev_total = _fund_request_previous_cumulative(fund_request)
    current_total = Decimal(str(fund_request.total_amount or 0))
    grand_total = prev_total + current_total
    signature_path = _pdf_signature_path()
    approvals_left = Paragraph(
        f"1. MASM PRESIDENT'S {event_year} APPROVAL COPY<br/>2. QUOTATION / BANK / REQUEST COPIES",
        normal,
    )
    approvals_right = [Paragraph('FOR MASM', for_masm_style)]
    if signature_path:
        signature_image = Image(signature_path, width=34 * mm, height=14 * mm)
        signature_image.hAlign = 'RIGHT'
        approvals_right.append(signature_image)
    approvals_right.extend([
        Paragraph('R.Surendranath', right_small),
        Paragraph('JS - Social Welfare Activities', right_small),
    ])
    approval_table = Table([[approvals_left, approvals_right]], colWidths=[165 * mm, 108 * mm])
    approval_table.hAlign = 'LEFT'
    approval_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 10 * mm),
        ('LEFTPADDING', (1, 0), (1, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 8 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.extend([approval_table, Spacer(1, 10)])

    totals = Table([
        [Paragraph('<b>PREVIOUS CUMULATIVE(Rs.)</b>', normal), Paragraph(_pdf_currency(prev_total), totals_value_style)],
        [Paragraph('<b>CURRENT FUND REQUEST(Rs.)</b>', normal), Paragraph(_pdf_currency(current_total), totals_value_style)],
        [Paragraph('<b>TOTAL(Rs.)</b>', normal), Paragraph(_pdf_currency(grand_total), totals_value_style)],
    ], colWidths=[205 * mm, 68 * mm])
    totals.hAlign = 'LEFT'
    totals.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#e5e7eb')),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.extend([totals, Spacer(1, 10)])

    def draw_footer(canvas, _doc_obj):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(doc.leftMargin, 8 * mm, fund_request.formatted_fund_request_number or 'Draft')
        canvas.drawCentredString(landscape(A4)[0] / 2, 8 * mm, f'Page {canvas.getPageNumber()}')
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)
    return buffer


def generate_purchase_order_pdf(purchase_order: models.PurchaseOrder) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("po-normal", parent=styles["BodyText"], fontSize=9, leading=11)
    small = ParagraphStyle("po-small", parent=normal, fontSize=8.5, leading=10)
    center_title = ParagraphStyle(
        "po-title",
        parent=styles["Heading2"],
        alignment=1,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=20,
        textColor=colors.HexColor("#008000"),
        spaceAfter=4,
    )
    meta_right = ParagraphStyle(
        "po-meta-right",
        parent=normal,
        alignment=2,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
    )
    green_header = colors.HexColor("#008000")
    light_border = colors.HexColor("#e5e7eb")

    logo_path = _pdf_logo_path()
    guru_logo_path = _pdf_guru_logo_path()
    signature_path = _pdf_signature_path()
    left_logo = _fitted_pdf_image(guru_logo_path, max_width_mm=28, max_height_mm=24)
    right_logo = _fitted_pdf_image(logo_path, max_width_mm=28, max_height_mm=24)

    po_number = purchase_order.purchase_order_number or next_purchase_order_number()
    current_date = timezone.localtime(purchase_order.created_at).strftime("%d-%m-%y") if purchase_order.created_at else timezone.localdate().strftime("%d-%m-%y")

    left_block = [
        left_logo,
        Spacer(1, 3),
        Paragraph("Melmaruvathur Adhiparasakthi Spiritual Movement", small),
        Paragraph("GST Road, Melmaruvathur 603319", small),
        Paragraph("Chengalpet District, Tamilnadu", small),
        Paragraph("GST NO: 33AACTM0073D1Z5.", small),
        Paragraph("Email: maruvoorhelp@gmail.com", small),
    ]
    center_block = [Spacer(1, 14), Paragraph("PURCHASE ORDER", center_title)]
    right_block = [
        right_logo,
        Spacer(1, 3),
        Paragraph(f"PO No: {po_number}", meta_right),
        Paragraph(f"DATE: {current_date}", meta_right),
    ]

    header = Table([[left_block, center_block, right_block]], colWidths=[60 * mm, 70 * mm, 58 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    vendor_lines = [
        Paragraph(purchase_order.vendor_name or "-", normal),
        Paragraph((purchase_order.vendor_address or "-").replace("\n", "<br/>"), small),
        Paragraph(
            ", ".join(
                part for part in [
                    purchase_order.vendor_city or "",
                    purchase_order.vendor_state or "",
                    purchase_order.vendor_pincode or "",
                ] if part
            ) or "-",
            small,
        ),
        Paragraph(f"GST No: {purchase_order.gst_number or '-'}", small),
    ]
    ship_to_lines = [
        Paragraph("Melmaruvathur Adhiparasakthi Spiritual Movement", small),
        Paragraph("GST Road, Melmaruvathur 603319", small),
        Paragraph("Chengalpet District, Tamilnadu", small),
    ]
    vendor_table = Table(
        [
            [
                Paragraph("<b>VENDOR</b>", ParagraphStyle("po-section-head", parent=small, textColor=colors.white)),
                Paragraph("<b>SHIP TO</b>", ParagraphStyle("po-section-head-right", parent=small, textColor=colors.white)),
            ],
            [vendor_lines, ship_to_lines],
        ],
        colWidths=[91 * mm, 91 * mm],
    )
    vendor_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), green_header),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BOX", (0, 1), (-1, 1), 0.5, light_border),
        ("INNERGRID", (0, 1), (-1, 1), 0.5, light_border),
    ]))

    header_left = ParagraphStyle(
        "po-header-left",
        parent=small,
        alignment=0,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    header_center = ParagraphStyle(
        "po-header-center",
        parent=small,
        alignment=1,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    item_rows = [[
        Paragraph('ITEM NAME', header_left),
        Paragraph('DESCRIPTION', header_left),
        Paragraph('QTY', header_center),
        Paragraph('UNIT PRICE', header_center),
        Paragraph('TOTAL<br/><font size="8">(Inclusive of Tax)</font>', header_center),
    ]]
    total_amount = Decimal("0")
    for item in purchase_order.items.all():
        line_total = Decimal(str(item.total_value or 0))
        total_amount += line_total
        item_rows.append([
            Paragraph(item.supplier_article_name or item.article_name or "-", ParagraphStyle("po-item-left", parent=small, alignment=0)),
            Paragraph((item.description or "").replace("\n", "<br/>") or "-", ParagraphStyle("po-desc-left", parent=small, alignment=0)),
            str(item.quantity or 0),
            _pdf_currency(item.unit_price or 0),
            _pdf_currency(line_total),
        ])
    item_rows.append([
        Paragraph("", small),
        Paragraph("", small),
        Paragraph("", small),
        Paragraph("<b>TOTAL<br/><font size='8'>(Inclusive of Tax)</font></b>", ParagraphStyle("po-total-label", parent=small, alignment=1)),
        f"{_pdf_currency(total_amount)}",
    ])

    item_table = Table(item_rows, colWidths=[46 * mm, 46 * mm, 18 * mm, 36 * mm, 36 * mm], repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), green_header),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, light_border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 1), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (4, 0), "CENTER"),
        ("ALIGN", (2, 1), (4, -1), "CENTER"),
        ("FONTNAME", (2, 1), (4, -2), "Helvetica"),
        ("FONTSIZE", (2, 1), (4, -2), 8.5),
        ("TEXTCOLOR", (2, 1), (4, -2), colors.black),
        ("FONTNAME", (4, -1), (4, -1), "Helvetica-Bold"),
        ("FONTSIZE", (4, -1), (4, -1), 8.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (2, 0), (4, -1), 0),
        ("RIGHTPADDING", (2, 0), (4, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f5f5f5")),
    ]))

    comments_text = (purchase_order.comments or "").strip() or models.PURCHASE_ORDER_DEFAULT_COMMENTS
    comments_text = escape(comments_text).replace("\n", "<br/>")
    comments_table = Table(
        [
            [Paragraph('<font color="white"><b>Comments or Special Instructions</b></font>', small)],
            [Paragraph(comments_text, small)],
        ],
        colWidths=[182 * mm],
    )
    comments_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), green_header),
        ("BOX", (0, 1), (0, 1), 0.5, light_border),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 24),
    ]))

    signature_bits = [Paragraph("<b>Authorised Signatory</b>", small)]
    if signature_path:
        signature_image = Image(signature_path, width=34 * mm, height=14 * mm)
        signature_image.hAlign = "LEFT"
        signature_bits.append(signature_image)
    signature_bits.extend([
        Paragraph("R.Surendranath", small),
        Paragraph("JS - Social Welfare Activities", small),
    ])

    story = [
        header,
        Spacer(1, 10),
        vendor_table,
        Spacer(1, 12),
        item_table,
        Spacer(1, 12),
        comments_table,
        Spacer(1, 10),
        Table([[signature_bits]], colWidths=[70 * mm], hAlign="LEFT", style=TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])),
    ]

    def draw_footer(canvas, _doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, "If you have any questions about this purchase order, please contact")
        canvas.drawCentredString(A4[0] / 2, 6 * mm, "+91 98400 46263, maruvoorhelp@gmail.com")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)
    return buffer


def sync_fund_request_totals(fund_request: models.FundRequest) -> None:
    with transaction.atomic():
        if fund_request.fund_request_type == models.FundRequestTypeChoices.AID:
            total_value = models.FundRequestRecipient.objects.filter(fund_request=fund_request).aggregate(
                total=Sum("fund_requested")
            ).get("total") or 0
        else:
            total_value = models.FundRequestArticle.objects.filter(fund_request=fund_request).aggregate(
                total=Sum("value")
            ).get("total") or 0
        fund_request.total_amount = total_value
        fund_request.save(update_fields=["total_amount"])


def sync_purchase_order_totals(purchase_order: models.PurchaseOrder) -> None:
    with transaction.atomic():
        total_value = models.PurchaseOrderItem.objects.filter(purchase_order=purchase_order).aggregate(
            total=Sum("total_value")
        ).get("total") or 0
        purchase_order.total_amount = total_value
        purchase_order.save(update_fields=["total_amount"])


def log_audit(
    *,
    user: Optional[models.AppUser],
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    details: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    models.AuditLog.objects.create(
        user=user,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def mark_fund_request_status(
    fund_request: models.FundRequest,
    status: models.FundRequestStatusChoices,
    actor: Optional[models.AppUser] = None,
) -> models.FundRequest:
    prev = fund_request.status
    fund_request.status = status
    if status in {models.FundRequestStatusChoices.SUBMITTED, models.FundRequestStatusChoices.APPROVED, models.FundRequestStatusChoices.REJECTED}:
        sync_fund_request_totals(fund_request)
    fund_request.save(update_fields=["status"])
    log_audit(
        user=actor,
        action_type=models.ActionTypeChoices.STATUS_CHANGE,
        entity_type="fund_request",
        entity_id=str(fund_request.id),
        details={"from": prev, "to": status},
    )
    return fund_request


LABEL_LAYOUTS = {
    "12L": {
        "page_size": portrait(A4),
        "top_margin": 9 * mm,
        "side_margin": 4 * mm,
        "vertical_pitch": 47 * mm,
        "horizontal_pitch": 102 * mm,
        "label_height": 44 * mm,
        "label_width": 100 * mm,
        "number_across": 2,
        "number_down": 6,
        "token_font": 60,
        "token_font_medium": 50,
        "token_font_small": 47,
        "line_font": 15,
        "line_leading": 16,
        "name_leading": 14,
        "name_space_after": 20,
        "article_y": 6 * mm,
        "name_vertical_factor": 0.85,
    },
    "2L": {
        "page_size": portrait(A4),
        "top_margin": 2.5 * mm,
        "side_margin": 5 * mm,
        "vertical_pitch": 146 * mm,
        "horizontal_pitch": 200 * mm,
        "label_height": 146 * mm,
        "label_width": 200 * mm,
        "number_across": 1,
        "number_down": 2,
        "token_font": 80,
        "token_font_medium": 80,
        "token_font_small": 70,
        "line_font": 35,
        "line_leading": 35,
        "name_leading": 35,
        "name_space_after": 0,
        "article_y": 35 * mm,
        "name_vertical_factor": 0.66,
    },
    "A4": {
        "page_size": landscape(A4),
        "top_margin": 12 * mm,
        "side_margin": 12 * mm,
        "vertical_pitch": 0,
        "horizontal_pitch": 0,
        "label_height": landscape(A4)[1] - 24 * mm,
        "label_width": landscape(A4)[0] - 24 * mm,
        "number_across": 1,
        "number_down": 1,
    },
}


def _label_token_font_size(token_text: str, config: dict) -> int:
    if len(token_text) >= 4:
        return config["token_font_small"]
    if len(token_text) == 3:
        return config["token_font_medium"]
    return config["token_font"]


def _draw_standard_label(pdf_canvas, entry: dict, *, x: float, y: float, config: dict) -> None:
    token_text = str(entry.get("token") or "")
    name_text = str(entry.get("name") or "")
    article_text = str(entry.get("article") or "")

    token_style = ParagraphStyle(
        name=f"token-{config['label_width']}",
        fontSize=_label_token_font_size(token_text, config),
        alignment=0,
    )
    article_style = ParagraphStyle(
        name=f"article-{config['label_width']}",
        fontSize=config["line_font"],
        leading=config["line_leading"],
        alignment=1,
    )
    name_style = ParagraphStyle(
        name=f"name-{config['label_width']}",
        fontSize=config["line_font"],
        leading=config["name_leading"],
        spaceAfter=config.get("name_space_after", 0),
        alignment=1,
    )

    token_para = Paragraph(f"<b>{escape(token_text)}</b>", token_style)
    article_para = Paragraph(f"<b>{escape(article_text)}</b>", article_style)
    name_para = Paragraph(f"<b>{escape(name_text)}</b>", name_style)

    label_width = config["label_width"]
    label_height = config["label_height"]

    token_width, token_height = token_para.wrap(label_width / 2, label_height)
    token_para.drawOn(pdf_canvas, x + 8 * mm, y + 0.66 * (label_height - token_height))

    name_width, name_height = name_para.wrap(label_width / 2, label_height)
    name_para.drawOn(
        pdf_canvas,
        x + 0.8 * (label_width - name_width),
        y + config["name_vertical_factor"] * (label_height - name_height),
    )

    article_width, article_height = article_para.wrap(label_width / 2, label_height)
    article_para.drawOn(pdf_canvas, x + 0.8 * (label_width - article_width), y + config["article_y"])


def generate_mnp_labels_pdf(entries: list[dict], *, layout: str = "12L", mode: str = "continuous") -> io.BytesIO:
    config = LABEL_LAYOUTS[layout]
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=config["page_size"])
    _width, height = config["page_size"]
    per_page = config["number_across"] * config["number_down"]
    slot_index = 0
    current_group = None

    for entry in entries:
        group_key = str(entry.get("group") or "")
        if mode == "separate" and current_group is not None and group_key != current_group:
            pdf_canvas.showPage()
            slot_index = 0
        elif slot_index and slot_index % per_page == 0:
            pdf_canvas.showPage()
            slot_index = 0

        current_group = group_key if mode == "separate" else current_group
        col = slot_index % config["number_across"]
        row = slot_index // config["number_across"] % config["number_down"]
        x = config["side_margin"] + col * config["horizontal_pitch"]
        y = height - config["top_margin"] - row * config["vertical_pitch"] - config["label_height"]
        _draw_standard_label(pdf_canvas, entry, x=x, y=y, config=config)
        slot_index += 1

    pdf_canvas.save()
    buffer.seek(0)
    return buffer


def generate_mnp_custom_labels_pdf(entries, *, layout: str = "12L") -> io.BytesIO:
    config = LABEL_LAYOUTS[layout]
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=config["page_size"])
    _width, height = config["page_size"]
    per_page = config["number_across"] * config["number_down"]
    default_font_size = 72 if layout == "A4" else 30 if layout == "12L" else 54

    normalized_entries = []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                text = str(entry.get("text") or "").strip()
                count = int(entry.get("count") or 0)
                font_size = int(entry.get("font_size") or default_font_size)
                line_spacing = entry.get("line_spacing")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                text = str(entry[0] or "").strip()
                count = int(entry[1] or 0)
                font_size = int(entry[2] or default_font_size) if len(entry) >= 3 else default_font_size
                line_spacing = int(entry[3] or 0) if len(entry) >= 4 else None
            else:
                text = str(entry or "").strip()
                count = 1
                font_size = default_font_size
                line_spacing = None
            font_size = max(8, min(font_size, 120))
            if line_spacing is not None:
                line_spacing = max(0, min(int(line_spacing), 120))
            if text and count > 0:
                normalized_entries.extend([{"text": text, "font_size": font_size, "line_spacing": line_spacing}] * count)
    else:
        text = str(entries or "").strip()
        if text:
            normalized_entries.append({"text": text, "font_size": default_font_size, "line_spacing": None})

    def _custom_label_markup(raw_text: str) -> str:
        escaped = escape(str(raw_text or "").strip())
        escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
        escaped = escaped.replace("|", "<br/>").replace("\n", "<br/>")
        return escaped

    for index, entry in enumerate(normalized_entries):
        text = str(entry.get("text") or "").strip()
        font_size = int(entry.get("font_size") or default_font_size)
        line_spacing = entry.get("line_spacing")
        line_leading = font_size + (6 if layout == "A4" else 2 if layout == "12L" else 4)
        if line_spacing is not None:
            line_leading = font_size + max(0, min(int(line_spacing), 120))
        if index and index % per_page == 0:
            pdf_canvas.showPage()
        slot_index = index % per_page
        col = slot_index % config["number_across"]
        row = slot_index // config["number_across"] % config["number_down"]
        x = config["side_margin"] + col * config["horizontal_pitch"]
        y = height - config["top_margin"] - row * config["vertical_pitch"] - config["label_height"]

        style = ParagraphStyle(
            name=f"custom-{layout}-{font_size}",
            fontSize=font_size,
            leading=line_leading,
            alignment=1,
        )
        para = Paragraph(f"<b>{_custom_label_markup(text)}</b>", style)
        wrapped_width, wrapped_height = para.wrap(config["label_width"] - 10 * mm, config["label_height"] - 10 * mm)
        para.drawOn(
            pdf_canvas,
            x + (config["label_width"] - wrapped_width) / 2,
            y + (config["label_height"] - wrapped_height) / 2,
        )

    pdf_canvas.save()
    buffer.seek(0)
    return buffer
