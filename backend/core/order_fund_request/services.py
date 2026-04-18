from __future__ import annotations

"""Service functions for order fund request workflows."""

import io
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import models
from core.shared.audit import log_audit
from core.shared.pdf_utils import _fitted_pdf_image
from core.shared.pdf_utils import _pdf_currency
from core.shared.pdf_utils import _pdf_guru_logo_path
from core.shared.pdf_utils import _pdf_logo_path
from core.shared.pdf_utils import _pdf_signature_path


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
        return models.PublicBeneficiaryEntry.objects.active().select_related("article").filter(pk=source_id).first()
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
    if article.public_entries.exclude(status=models.BeneficiaryStatusChoices.ARCHIVED).exists():
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


def _fund_request_ordinal(value: int) -> str:
    from core.shared.format_utils import _ordinal

    return _ordinal(value)

def _event_programme_title(event_year: int) -> str:
    birthday_number = max(event_year - 1940, 1)
    return (
        'Payment Request Details for MASM Makkal Nala Pani Programme on the eve of '
        f'{_fund_request_ordinal(birthday_number)} Birthday Celebrations of His Holiness AMMA at '
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
