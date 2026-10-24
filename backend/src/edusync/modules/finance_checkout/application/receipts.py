"""Receipt PDF, generated on demand from the committed ledger (never part of the payment transaction).

Layout status: functional receipt built only from ledger facts (school identity, receipt number, date,
cashier, pupil, class, year, allocations, advance). Conformity with the certified Desktop receipt layout
is TO BE CONFIRMED BY THE OWNER (golden master not available in this repository).
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from edusync.modules.documents.application.identity import signatory_line
from edusync.modules.documents.application.object_store import logo_stream
from edusync.modules.finance_reports.domain.periodic import money_in_words

DARK = colors.HexColor("#123A8C")
MUTED = colors.HexColor("#475467")
LINE = colors.HexColor("#D0D5DD")


def money(value: Any, currency: str) -> str:
    q = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, cents = f"{q:,.2f}".partition(".")
    text = whole.replace(",", " ")
    return f"{text}{'' if cents == '00' else ',' + cents} {currency}"


def _styles(narrow: bool):
    base = 7.4 if narrow else 8.6
    return {
        "school": ParagraphStyle("school", fontName="Helvetica-Bold", fontSize=base + 3, leading=base + 5, textColor=DARK, alignment=TA_CENTER),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=base - 1, leading=base + 1, textColor=MUTED, alignment=TA_CENTER),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=base + 2, leading=base + 4, textColor=DARK, alignment=TA_CENTER, spaceBefore=4),
        "copy": ParagraphStyle("copy", fontName="Helvetica-Bold", fontSize=base, leading=base + 2, textColor=colors.HexColor("#B42318"), alignment=TA_CENTER),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=base, leading=base + 2),
        "bold": ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=base, leading=base + 2),
        "right": ParagraphStyle("right", fontName="Helvetica", fontSize=base, leading=base + 2, alignment=TA_RIGHT),
        "rightb": ParagraphStyle("rightb", fontName="Helvetica-Bold", fontSize=base + 1, leading=base + 3, alignment=TA_RIGHT),
        "foot": ParagraphStyle("foot", fontName="Helvetica", fontSize=base - 1.5, leading=base, textColor=MUTED, alignment=TA_CENTER),
    }


def _story(school: dict[str, Any], r: dict[str, Any], width: float, narrow: bool) -> list:
    st = _styles(narrow)
    contacts = " · ".join(str(x) for x in (school.get("address"), school.get("city"), school.get("phone")) if x)
    ident = [Paragraph(escape(str(school.get("name") or "École")), st["school"])]
    if school.get("motto"):                         # Desktop identity « devise / mention »
        ident.append(Paragraph(f"<i>{escape(str(school['motto']))}</i>", st["meta"]))
    if contacts:
        ident.append(Paragraph(escape(contacts), st["meta"]))
    logo = logo_stream(school)
    size = 12 * mm if narrow else 15 * mm
    head = Table([[Image(logo, width=size, height=size) if logo else "", ident]], colWidths=[size + 2 * mm, width - size - 2 * mm]) if logo else Table([[ident]], colWidths=[width])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story = [head, Paragraph("REÇU DE PAIEMENT", st["title"]), Paragraph(f"N° {escape(r['receipt_number'])}", st["title"])]
    if r["copy_no"] > 1:
        story.append(Paragraph(f"DUPLICATA n° {r['copy_no'] - 1}", st["copy"]))
    if r.get("exemplar"):
        story.append(Paragraph(f"Exemplaire {r['exemplar'][0]}/{r['exemplar'][1]}", st["copy"]))
    story.append(Spacer(1, 2 * mm))
    who = [
        ("Date", r["created_at"].strftime("%d/%m/%Y %H:%M")),
        ("Élève", " ".join(x for x in (r.get("last_name"), r.get("middle_name"), r.get("first_name")) if x) or "—"),
        ("Matricule", r.get("matricule") or "—"),
        ("Classe", f"{r.get('class_label') or '—'} · {r.get('academic_year') or ''}".strip(" ·")),
        ("Caissier", r.get("cashier") or "—"),
    ]
    info = Table([[Paragraph(k, st["bold"]), Paragraph(escape(str(v)), st["cell"])] for k, v in who], colWidths=[width * 0.3, width * 0.7])
    info.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [info, Spacer(1, 2.5 * mm)]
    rows = [[Paragraph("Désignation", st["bold"]), Paragraph("Montant", st["rightb"])]]
    for line in r["lines"]:
        rows.append([Paragraph(escape(str(line["label"])), st["cell"]), Paragraph(money(line["amount"], r["currency"]), st["right"])])
    if r.get("advance_amount"):
        rows.append([Paragraph(escape(f"Avance conservée — {r.get('advance_target') or 'échéances futures'}"), st["cell"]), Paragraph(money(r["advance_amount"], r["currency"]), st["right"])])
    rows.append([Paragraph("TOTAL REÇU", st["bold"]), Paragraph(money(r["amount"], r["currency"]), st["rightb"])])
    table = Table(rows, colWidths=[width * 0.62, width * 0.38], repeatRows=1)
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.6, DARK), ("LINEABOVE", (0, -1), (-1, -1), 0.6, DARK),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    story += [table, Spacer(1, 2.5 * mm)]
    # N3-G / G-DOC-1 — Desktop receipt block « MONTANT EN LETTRES » (money_in_words).
    words = money_in_words(r["amount"], r["currency"])
    story += [Paragraph("MONTANT EN LETTRES :", st["bold"]), Paragraph(escape(words[:1].upper() + words[1:] + "."), st["cell"]), Spacer(1, 3 * mm)]
    signer = signatory_line(school)              # Desktop save_document_settings signatory
    if signer:
        story += [Paragraph("Signature et cachet", st["foot"]), Spacer(1, 9 * mm), Paragraph(escape(signer), st["meta"]), Spacer(1, 2 * mm)]
    story.append(Paragraph("Montant enregistré dans la caisse de l'école. Conservez ce reçu.", st["foot"]))
    story.append(Paragraph("Édité par EduSync", st["foot"]))
    return story


def receipt_pdf(*, school: dict[str, Any], receipts: list[dict[str, Any]], fmt: str = "A5", copies: int = 1) -> bytes:
    """One receipt per page. fmt: A5 (portrait sheet), 80MM or 58MM (thermal rolls). Desktop parity (lot L7): each receipt is
    produced `copies` times (1..5), every copy numbered."""
    buf = BytesIO()
    narrow = fmt in ("80MM", "58MM")
    copies = max(1, min(5, int(copies or 1)))
    if copies > 1:
        receipts = [{**r, "exemplar": (n, copies)} for r in receipts for n in range(1, copies + 1)]
    if narrow:
        roll = 80 if fmt == "80MM" else 58
        page = (roll * mm, 200 * mm + 8 * mm * max(len(r["lines"]) for r in receipts))
        margins = dict(leftMargin=4 * mm, rightMargin=4 * mm, topMargin=4 * mm, bottomMargin=4 * mm)
    else:
        page = A5
        margins = dict(leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    doc = SimpleDocTemplate(buf, pagesize=page, title="Reçu de paiement", author="EduSync", **margins)
    width = page[0] - margins["leftMargin"] - margins["rightMargin"]
    story: list = []
    for i, r in enumerate(receipts):
        if i:
            story.append(PageBreak())
        story += _story(school, r, width, narrow)
    doc.build(story)
    return buf.getvalue()
