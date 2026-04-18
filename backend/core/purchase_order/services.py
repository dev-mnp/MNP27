"""Service functions for the purchase_order module."""

import io
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import models
from core.shared.pdf_utils import _fitted_pdf_image
from core.shared.pdf_utils import _pdf_currency
from core.shared.pdf_utils import _pdf_guru_logo_path
from core.shared.pdf_utils import _pdf_logo_path
from core.shared.pdf_utils import _pdf_signature_path


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


def sync_purchase_order_totals(purchase_order: models.PurchaseOrder) -> None:
    with transaction.atomic():
        total_value = models.PurchaseOrderItem.objects.filter(purchase_order=purchase_order).aggregate(
            total=Sum("total_value")
        ).get("total") or 0
        purchase_order.total_amount = total_value
        purchase_order.save(update_fields=["total_amount"])


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
        Paragraph("ITEM NAME", header_left),
        Paragraph("DESCRIPTION", header_left),
        Paragraph("QTY", header_center),
        Paragraph("UNIT PRICE", header_center),
        Paragraph("TOTAL<br/><font size=\"8\">(Inclusive of Tax)</font>", header_center),
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
