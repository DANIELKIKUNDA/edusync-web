"""Official school receipt: documentary grid matched to Desktop golden documents.py.

Generated from committed ledger facts on demand.  No printer or browser action is
part of the payment transaction; signature and stamp areas stay genuinely blank.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.utils import simpleSplit

from edusync.modules.documents.application.object_store import logo_stream
from edusync.modules.finance_reports.domain.periodic import money_in_words


def money(value: Any, currency: str) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, cents = f"{amount:,.2f}".partition(".")
    number = whole.replace(",", " ")
    return f"{number}{'' if cents == '00' else ',' + cents} {'FC' if currency == 'CDF' else currency}"


def _amount(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    whole, _, cents = f"{amount:,.2f}".partition(".")
    return whole.replace(",", " ") + ("" if cents == "00" else "," + cents)


THERMAL_80_WIDTH = 72 * mm


def _size(fmt: str, lines: int) -> tuple[float, float]:
    if fmt == "58MM":
        return 58 * mm, max(205, 190 + lines * 8) * mm
    if fmt == "80MM":
        # Owner, 2026-11-18: an 80 mm roll prints only 72 mm (XP-80C driver « 80(72.1) x 297 mm ») — a page of 80 mm
        # was clipped on the right. The page IS the printable width; its height follows the content (set when drawn).
        return THERMAL_80_WIDTH, max(120, 110 + lines * 6) * mm
    if fmt == "A4":
        return A4
    if fmt == "A5":
        return A5
    raise ValueError("Format de reçu inconnu")


def _text(pdf: canvas.Canvas, value: Any, x: float, y: float, size: float,
          *, font: str = "Helvetica", align: str = "left", width: float | None = None,
          color=colors.black) -> None:
    label = str(value or "")
    if width is not None:
        while size > 3.3 and stringWidth(label, font, size) > width:
            size -= .2
        if stringWidth(label, font, size) > width:
            while label and stringWidth(label + "…", font, size) > width:
                label = label[:-1]
            label += "…"
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    if align == "center":
        pdf.drawCentredString(x, y, label)
    elif align == "right":
        pdf.drawRightString(x, y, label)
    else:
        pdf.drawString(x, y, label)
    pdf.setFillColor(colors.black)


def _box(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fill=None) -> None:
    if fill is not None:
        pdf.setFillColor(fill)
        pdf.rect(x, y, w, h, fill=1, stroke=1)
        pdf.setFillColor(colors.black)
    else:
        pdf.rect(x, y, w, h, fill=0, stroke=1)


def _draw(pdf: canvas.Canvas, school: dict[str, Any], row: dict[str, Any],
          fmt: str, copy_index: int, copies: int) -> None:
    lines = list(row.get("lines") or [])
    if row.get("advance_amount"):
        lines.append({"fee_label": "Avance conservée", "period_label": row.get("advance_target") or "Échéances futures",
                      "amount": row["advance_amount"]})
    width, height = _size(fmt, len(lines))
    pdf.setPageSize((width, height))
    thermal = tiny = fmt == "58MM"
    margin = (1.8 if thermal else 4) * mm
    left, right, top, bottom = margin, width - margin, height - margin, margin
    usable = right - left
    pdf.setLineWidth(.55 if thermal else .8)
    pdf.rect(left, bottom, usable, top - bottom, fill=0, stroke=1)

    # Header: same three areas as the Desktop 80 mm and A5 templates.
    header_h = (32 if thermal else 35) * mm
    y0 = top - header_h
    pdf.line(left, y0, right, y0)
    logo_w = (12 if tiny else 15 if thermal else 23) * mm
    number_w = (17 if tiny else 20 if thermal else 32) * mm
    middle_left, middle_right = left + logo_w + 1.5 * mm, right - number_w - 1.5 * mm
    logo = logo_stream(school)
    if logo:
        try:
            pdf.drawImage(ImageReader(logo), left + 1.2 * mm, y0 + 4 * mm,
                          width=logo_w - 2.4 * mm, height=header_h - 8 * mm,
                          preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:
            _text(pdf, "ÉCOLE", left + logo_w / 2, y0 + header_h / 2, 5.5 if thermal else 8,
                  font="Helvetica-Bold", align="center")
    else:
        _text(pdf, "ÉCOLE", left + logo_w / 2, y0 + header_h / 2, 5.5 if thermal else 8,
              font="Helvetica-Bold", align="center")
    center = (middle_left + middle_right) / 2
    middle_w = middle_right - middle_left
    _text(pdf, (school.get("motto") or "ÉTABLISSEMENT SCOLAIRE").upper(), center, top - 6 * mm,
          4.8 if tiny else 5.5 if thermal else 8.5, font="Helvetica-Bold", align="center", width=middle_w)
    _text(pdf, (school.get("name") or "École").upper(), center, top - 12 * mm,
          7 if tiny else 8.4 if thermal else 14.5, font="Helvetica-Bold", align="center", width=middle_w)
    address = " · ".join(str(x) for x in (school.get("address"), school.get("city"), school.get("province")) if x)
    _text(pdf, address, center, top - 18 * mm, 4.2 if tiny else 4.8 if thermal else 7.2,
          align="center", width=middle_w)
    _text(pdf, f"Tél. : {school['phone']}" if school.get("phone") else "", center, top - 23 * mm,
          4.2 if tiny else 4.8 if thermal else 7, align="center", width=middle_w)
    _text(pdf, f"E-mail : {school['email']}" if school.get("email") else "", center, top - 28 * mm,
          4 if tiny else 4.5 if thermal else 6.8, align="center", width=middle_w)
    nx, ny, nh = right - number_w, y0 + 5 * mm, header_h - 10 * mm
    _box(pdf, nx, ny, number_w, nh)
    _text(pdf, "REÇU N°", nx + number_w / 2, ny + nh - 6 * mm, 5 if thermal else 8.2,
          font="Helvetica-Bold", align="center")
    _text(pdf, row.get("receipt_number") or "—", nx + number_w / 2, ny + 5 * mm,
          5.8 if tiny else 6.6 if thermal else 11.5, font="Helvetica-Bold",
          align="center", width=number_w - 2 * mm, color=colors.red)

    # Year / class / date / time band.
    band_h = (14 if thermal else 16) * mm
    y = y0 - band_h
    created = row.get("created_at")
    if isinstance(created, datetime):
        date_value, time_value = created.strftime("%d/%m/%Y"), created.strftime("%H:%M:%S")
    else:
        date_value, time_value = str(created or "")[:10], "—"
    band = [("ANNÉE SCOLAIRE", row.get("academic_year") or "—"),
            ("CLASSE", row.get("class_label") or "—"), ("DATE", date_value), ("HEURE", time_value)]
    x = left
    for ratio, (label, value) in zip((.24, .31, .25, .20), band):
        w = usable * ratio
        _box(pdf, x, y, w, band_h)
        _text(pdf, label, x + w / 2, y + band_h - 5 * mm, 4.5 if thermal else 7,
              font="Helvetica-Bold", align="center", width=w - 2 * mm)
        _text(pdf, value, x + w / 2, y + 4 * mm, 5.2 if thermal else 8.4,
              align="center", width=w - 2 * mm)
        x += w
    y -= 10 * mm
    _text(pdf, "REÇU DE PAIEMENT", width / 2, y + 3 * mm, 8.2 if tiny else 9.8 if thermal else 16,
          font="Helvetica-Bold", align="center")

    # Student identification, with no invented family or sex value.
    student_h = (31 if thermal else 33) * mm
    y -= student_h
    _box(pdf, left, y, usable, student_h)
    label_x = left + (3 if thermal else 5) * mm
    colon_x = left + (25 if tiny else 28 if thermal else 31) * mm
    value_x = colon_x + (3 if thermal else 4) * mm
    rows = [("CODE ÉLÈVE", row.get("matricule") or "—"), ("NOM", row.get("last_name") or "—"),
            ("POSTNOM", row.get("middle_name") or "—"), ("PRÉNOM", row.get("first_name") or "—"),
            ("SEXE", row.get("gender") or "—")]
    for index, (label, value) in enumerate(rows, 1):
        ry = y + student_h - index * student_h / 6
        _text(pdf, label, label_x, ry, 5.2 if thermal else 8,
              font="Helvetica-Bold", width=colon_x - label_x - mm)
        _text(pdf, ":", colon_x, ry, 5.2 if thermal else 8, font="Helvetica-Bold")
        _text(pdf, value, value_x, ry, 5.5 if thermal else 8.5,
              font="Helvetica-Bold", width=right - value_x - 3 * mm)

    # Detailed allocations, identical five-column hierarchy to the Desktop template.
    title_h = (8 if thermal else 9) * mm
    y -= title_h
    _box(pdf, left, y, usable, title_h)
    _text(pdf, "DÉTAIL DES PAIEMENTS", width / 2, y + title_h / 2 - 1.7 * mm,
          6.5 if thermal else 10.2, font="Helvetica-Bold", align="center")
    header_h = 7 * mm
    y -= header_h
    ratios = (.07, .25, .27, .18, .23)
    currency = "FC" if row.get("currency") == "CDF" else row.get("currency") or "—"
    headings = ("N°", "TYPE DE FRAIS", "LIBELLÉ / MOIS", "PÉRIODE", f"MONTANT ({currency})")
    x = left
    for ratio, label in zip(ratios, headings):
        w = usable * ratio
        _box(pdf, x, y, w, header_h, colors.HexColor("#F2F4F7"))
        _text(pdf, label, x + w / 2, y + 2.2 * mm, 4.2 if thermal else 6.5,
              font="Helvetica-Bold", align="center", width=w - mm)
        x += w
    for index, line in enumerate(lines, 1):
        y -= 6.5 * mm
        fee = str(line.get("fee_label") or line.get("label") or "Frais")
        period, period_value = _receipt_period(line, row.get("academic_year"))
        label = period or fee
        values = (str(index), fee, label, period_value or "—",
                  _amount(line.get("amount")))
        x = left
        for col, (ratio, value) in enumerate(zip(ratios, values)):
            w = usable * ratio
            _box(pdf, x, y, w, 6.5 * mm)
            align = "center" if col in (0, 3, 4) else "left"
            _text(pdf, value, x + w / 2 if align == "center" else x + mm, y + 2.1 * mm,
                  4.5 if thermal else 6.9, font="Helvetica-Bold" if col == 0 else "Helvetica",
                  align=align, width=w - 2 * mm)
            x += w
    y -= 9 * mm
    total_left = usable * sum(ratios[:-1])
    _box(pdf, left, y, total_left, 9 * mm, colors.HexColor("#F8F9FB"))
    _box(pdf, left + total_left, y, usable - total_left, 9 * mm, colors.HexColor("#F8F9FB"))
    _text(pdf, "TOTAL PAYÉ", left + total_left / 2, y + 3 * mm, 6.2 if thermal else 9.5,
          font="Helvetica-Bold", align="center")
    _text(pdf, f"{_amount(row.get('amount'))} {currency}", right - 1.5 * mm, y + 3 * mm,
          6.4 if thermal else 10.2, font="Helvetica-Bold", align="right",
          width=usable - total_left - 3 * mm)

    y -= 17 * mm
    _box(pdf, left, y, usable, 17 * mm)
    _text(pdf, "MONTANT EN LETTRES :", left + 2 * mm, y + 12 * mm, 5.4 if thermal else 8.2,
          font="Helvetica-Bold")
    words = money_in_words(row.get("amount") or 0, row.get("currency") or "CDF")
    words = words[:1].upper() + words[1:] + "."
    font_size = 5.2 if thermal else 8
    for index, sentence in enumerate(simpleSplit(words, "Helvetica-Oblique", font_size, usable - 4 * mm)[:2]):
        _text(pdf, sentence, left + 2 * mm, y + 7 * mm - index * (3.8 if thermal else 5) * mm,
              font_size, font="Helvetica-Oblique", width=usable - 4 * mm)

    y -= 15 * mm if thermal else 14 * mm
    _box(pdf, left, y, usable, 15 * mm if thermal else 14 * mm)
    _text(pdf, "MODE DE PAIEMENT :", left + 2 * mm, y + (10 if thermal else 9) * mm,
          5.2 if thermal else 8, font="Helvetica-Bold")
    mode = {"CASH": "ESPÈCES (CASH)", "MOBILE_MONEY": "MOBILE MONEY",
            "BANQUE": "BANQUE", "AUTRE": "AUTRE"}.get(str(row.get("payment_mode") or "").upper(), "—")
    _text(pdf, mode, left + (29 if thermal else 42) * mm, y + (10 if thermal else 9) * mm,
          5.2 if thermal else 8, width=usable - (31 if thermal else 44) * mm)
    note = " · ".join(x for x in (f"Réf. : {row['payment_reference']}" if row.get("payment_reference") else "",
                                  f"Famille : {row['family_name']}" if row.get("family_name") else "") if x)
    _text(pdf, note, left + 2 * mm, y + 4 * mm, 4.4 if thermal else 6.6, width=usable - 4 * mm)

    sign_h = (24 if thermal else 20) * mm
    y -= sign_h
    _box(pdf, left, y, usable, sign_h)
    half = usable / 2
    pdf.line(left + half, y, left + half, y + sign_h)
    _text(pdf, _cashier_label(row), left + half / 2, y + sign_h - 5 * mm, 5.4 if thermal else 8.2,
          font="Helvetica-Bold", align="center")
    _text(pdf, row.get("cashier") or "—", left + half / 2, y + sign_h - 11 * mm,
          5.1 if thermal else 7.8, align="center", width=half - 4 * mm)
    pdf.line(left + 4 * mm, y + 6 * mm, left + half - 4 * mm, y + 6 * mm)
    _text(pdf, "Signature", left + half / 2, y + 2.5 * mm, 4.2 if thermal else 6.2, align="center")
    _text(pdf, "CACHET DE L’ÉCOLE", left + half + half / 2, y + sign_h - 5 * mm,
          5.2 if thermal else 8, font="Helvetica-Bold", align="center")
    _text(pdf, "Zone réservée au cachet", left + half + half / 2, y + 8 * mm,
          4.2 if thermal else 6.2, align="center", width=half - 4 * mm,
          color=colors.HexColor("#667085"))
    footer = "Merci pour votre confiance."
    if copies > 1:
        footer += f"  Copie {copy_index}/{copies}."
    if row.get("copy_no", 1) > 1:
        footer += f"  DUPLICATA n° {row['copy_no'] - 1}."
    _text(pdf, f"* {footer} *", width / 2, max(bottom + 2.5 * mm, y - 5 * mm),
          4.4 if thermal else 6.8, font="Helvetica-Bold", align="center", width=usable - 4 * mm)


def _wrap_ticket(value: str, font: str, size: float, width: float) -> list[str]:
    """Wrap plain text and split an unusually long reference without shrinking it."""
    words = []
    for word in value.split():
        part = ""
        for char in word:
            if part and stringWidth(part + char, font, size) > width:
                words.append(part)
                part = ""
            part += char
        if part:
            words.append(part)
    return simpleSplit(" ".join(words), font, size, width)


def _cashier_label(row: dict[str, Any]) -> str:
    return {"M": "CAISSIER", "MME": "CAISSIÈRE"}.get(row.get("cashier_civility"), "ENCAISSEMENT EFFECTUÉ PAR")


def _receipt_period(item: dict[str, Any], academic_year: Any) -> tuple[str, str]:
    label = str(item.get("period_label") or "")
    value = str(item.get("period_value") or "")
    if item.get("periodicity") == "INSTALLMENT":
        number = item.get("sequence_order")
        if number:
            label = f"{number}{'re' if number == 1 else 'e'} tranche"
        return (f"Paiement de la {label}" if label else "Paiement par tranche"), ""
    if item.get("periodicity") == "MONTHLY" and label and len(value) == 7 and value[2] == "/":
        return f"{label} {value[3:]}", ""
    return label, value or str(academic_year or "")


def _draw_thermal_80(pdf: canvas.Canvas, school: dict[str, Any], row: dict[str, Any],
                     copy_index: int, copies: int) -> None:
    # Compact ticket (owner, 2026-11-18): 72 mm page = the printable width of an 80 mm roll, 3 mm inner margins, grouped
    # identity lines, tight spacing — less paper, nothing cut on the right.
    width, margin = THERMAL_80_WIDTH, 3 * mm
    usable = width - 2 * margin  # 66 mm
    marks: list[tuple[float, str, str, float, str]] = []
    rules: list[float] = []
    regular, bold = "Helvetica", "Helvetica-Bold"
    logo = logo_stream(school)
    cursor = 2 * mm
    header_width = usable - (12 * mm if logo else 0)
    body = 9

    def write(value: Any, size: float = body, font: str = regular, align: str = "left",
              line_width: float = usable) -> None:
        nonlocal cursor
        for line in _wrap_ticket(str(value), font, size, line_width):
            cursor += size
            marks.append((cursor, line, font, size, align))
            cursor += 1.8

    def separate() -> None:
        nonlocal cursor
        cursor += 1.5
        rules.append(cursor)
        cursor += 2.5

    def field(label: str, value: Any) -> None:
        write(f"{label} : {value or '—'}")

    currency = row.get("currency") or "CDF"
    symbol = "FC" if currency == "CDF" else currency
    header_align = "right" if logo else "center"
    write((school.get("name") or "École").upper(), 10.5, bold, header_align, header_width)
    write(" · ".join(str(school[k]) for k in ("address", "city", "province") if school.get(k)),
          8, align=header_align, line_width=header_width)
    contacts = " · ".join(f"{label} {school[key]}" for label, key in (("Tél.", "phone"), ("", "email")) if school.get(key))
    if contacts:
        write(contacts.strip(), 8, align=header_align, line_width=header_width)
    if logo:
        cursor = max(cursor, 12 * mm)
    separate()
    write("REÇU DE PAIEMENT", 11, bold, "center")
    write(f"REÇU N° {row.get('receipt_number') or '—'}", 9.5, bold, "center")
    if copies > 1:
        write(f"Copie {copy_index}/{copies}", align="center")
    if row.get("copy_no", 1) > 1:
        write(f"DUPLICATA n° {row['copy_no'] - 1}", body, bold, "center")
    created = row.get("created_at")
    stamp = created.strftime("%d/%m/%Y %H:%M") if isinstance(created, datetime) else str(created or "—")
    field("DATE / HEURE", stamp)
    name = " ".join(str(row[k]) for k in ("last_name", "middle_name", "first_name") if row.get(k))
    field("ÉLÈVE", name.upper() if name else None)
    write(f"CODE ÉLÈVE : {row.get('matricule') or '—'}" + (f" · SEXE : {row['gender']}" if row.get("gender") else ""))
    write(f"CLASSE : {row.get('class_label') or '—'} · ANNÉE SCOLAIRE : {row.get('academic_year') or '—'}")
    separate()
    write("DÉTAIL DES PAIEMENTS", body, bold)
    lines = list(row.get("lines") or [])
    if row.get("advance_amount"):
        lines.append({"fee_label": "Avance conservée", "period_label": row.get("advance_target") or "Échéances futures",
                      "amount": row["advance_amount"]})
    amount_width = 22 * mm
    label_width = usable - amount_width
    table_top = cursor + 1
    table_edges = [table_top]

    def table_row(labels: list[str], amounts: list[str], header: bool = False) -> None:
        nonlocal cursor
        row_height = 10.5 * max(len(labels), len(amounts)) + 3
        for index, line in enumerate(labels):
            marks.append((cursor + 10 + index * 10.5, line, bold if header else regular, body, "table-left"))
        for index, line in enumerate(amounts):
            marks.append((cursor + 10 + index * 10.5, line, bold, body, "table-right"))
        cursor += row_height
        table_edges.append(cursor + 1)

    table_row(["Frais / période"], ["Montant"], header=True)
    for item in lines:
        fee = item.get("fee_label") or item.get("label") or "Frais"
        period, period_value = _receipt_period(item, row.get("academic_year"))
        period = period or fee
        details = [str(fee)]
        if period != fee or period_value:
            details.append(" · ".join(str(value) for value in (period if period != fee else None, period_value) if value))
        labels = [line for detail in details for line in _wrap_ticket(detail, regular, body, label_width - 3 * mm)]
        amounts = _wrap_ticket(f"{_amount(item.get('amount'))} {symbol}", bold, body, amount_width - 3 * mm)
        table_row(labels, amounts)
    cursor += 2
    write(f"TOTAL PAYÉ : {_amount(row.get('amount'))} {symbol}", 13, bold, "center")
    words = money_in_words(row.get("amount") or 0, currency)
    write(f"MONTANT EN LETTRES : {words[:1].upper()}{words[1:]}.", 8)
    mode = {"CASH": "ESPÈCES (CASH)", "MOBILE_MONEY": "MOBILE MONEY", "BANQUE": "BANQUE",
            "AUTRE": "AUTRE"}.get(str(row.get("payment_mode") or "").upper())
    field("MODE DE PAIEMENT", mode)
    for label, key in (("Réf.", "payment_reference"), ("Famille", "family_name")):
        if row.get(key):
            field(label, row[key])
    field(_cashier_label(row), row.get("cashier"))
    separate()
    write("Signature et CACHET DE L’ÉCOLE : __________", 8)
    write("Merci pour votre confiance.", 8, align="center")

    height = cursor + 3 * mm
    pdf.setPageSize((width, height))
    if logo:
        try:
            pdf.drawImage(ImageReader(logo), margin, height - 12 * mm,
                          width=10 * mm, height=10 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    for top, label, font, size, align in marks:
        if align == "table-left":
            x, align = margin + 1.5 * mm, "left"
        elif align == "table-right":
            x, align = width - margin - 1.5 * mm, "right"
        else:
            x = width / 2 if align == "center" else width - margin if align == "right" else margin
        _text(pdf, label, x, height - top, size, font=font, align=align)
    for edge in table_edges:
        pdf.line(margin, height - edge, width - margin, height - edge)
    for x in (margin, margin + label_width, width - margin):
        pdf.line(x, height - table_top, x, height - table_edges[-1])
    for top in rules:
        pdf.line(margin, height - top, width - margin, height - top)


def receipt_pdf(*, school: dict[str, Any], receipts: list[dict[str, Any]],
                fmt: str = "80MM", copies: int = 1) -> bytes:
    """Render one official, numbered receipt per page, with optional numbered copies."""
    if not receipts:
        raise ValueError("Aucun reçu à produire")
    count = max(1, min(5, int(copies or 1)))
    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=_size(fmt, len(receipts[0].get("lines") or [])),
                        title="Reçu de paiement", author="EduSync")
    if fmt == "80MM":
        pdf.setViewerPreference("PrintScaling", "None")
    for row in receipts:
        for copy_index in range(1, count + 1):
            if fmt == "80MM":
                _draw_thermal_80(pdf, school, row, copy_index, count)
            else:
                _draw(pdf, school, row, fmt, copy_index, count)
            pdf.showPage()
    pdf.save()
    return out.getvalue()
