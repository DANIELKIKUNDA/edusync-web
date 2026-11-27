"""Printable grade sheet (V2 lot 3c): the teacher who prefers paper marks on it in class, then types or pastes the
column in a minute. Same letterhead as the other EduSync documents; standard PDF fonts only (no U+202F / U+00A0)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from edusync.modules.effectifs.application.documents import BLUE, BORDER, LIGHT, _header_block


def school_identity(conn, school_id) -> dict[str, Any]:
    from edusync.adapters.postgres_repositories import PostgresSchoolRepository
    from edusync.modules.documents.application.identity import apply_document_preferences
    school = PostgresSchoolRepository(conn).get(school_id)
    if not school:
        return {"name": "École"}
    logo = conn.execute(text("SELECT logo_object_key FROM school_branding WHERE school_id=:s"), {"s": str(school_id)}).scalar_one_or_none()
    return apply_document_preferences(conn, {"id": str(school_id), "name": school.name, "logo_object_key": logo, "email": school.email,
                                              "phone": school.phone, "address": school.address, "city": school.city, "province": school.province})


def grade_sheet_pdf(*, school: dict[str, Any], year_label: str, class_label: str, course_label: str, period_label: str, maximum: int,
                    pupils: list[dict], with_marks: bool) -> bytes:
    buf = BytesIO(); margin = 12 * mm; avail = A4[0] - 2 * margin
    title = "Fiche de cotation"
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=10 * mm, bottomMargin=12 * mm, title=title)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("c", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    ctx = f"{course_label} - {class_label} - {period_label} (sur {maximum}) | Année {year_label} | Éditée le {datetime.now():%d/%m/%Y}"
    story = _header_block(school, title, ctx, avail)
    data = [[Paragraph("N°", head), Paragraph("Nom, post-nom et prénom", head), Paragraph(f"Cote / {maximum}", head), Paragraph("Observation", head)]]
    present = [p for p in pupils if not p.get("departed")]
    for n, p in enumerate(present, start=1):
        mark = ""
        if with_marks:
            mark = {"ABSENT": "Abs.", "DISPENSE": "Disp."}.get(p.get("status") or "", "" if p.get("value") is None else str(p["value"]))
        data.append([str(n), Paragraph(p["name"], cell), mark, ""])
    table = Table(data, colWidths=[12 * mm, avail - 12 * mm - 30 * mm - 46 * mm, 30 * mm, 46 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE)), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor(BORDER)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT)]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"), ("ALIGN", (2, 0), (2, -1), "CENTER"), ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 8 * mm)]
    sign = Table([["Nom et signature de l'enseignant :", "Date :"]], colWidths=[avail * .65, avail * .35])
    sign.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 14)]))
    story.append(sign)
    doc.build(story)
    return buf.getvalue()
