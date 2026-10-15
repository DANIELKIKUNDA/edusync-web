"""N3-G — documents copied from the Desktop golden master (app/services/documents.py):
export_periodic_financial_report_pdf (official, numbered), export_periodic_financial_report_xlsx (companion, no number),
export_student_account_pdf (relevé du compte élève). FC and USD are never added together."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from edusync.modules.documents.application.object_store import logo_stream
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
from edusync.modules.finance_reports.domain.periodic import fr_date, period_display, periodic_title


def _money(v: Any) -> str:
    return f"{Decimal(str(v or 0)):,.2f}".replace(",", " ")


def _name(r: dict) -> str:
    return " ".join(x for x in [r.get("last_name"), r.get("middle_name"), r.get("first_name")] if x) or "—"


def periodic_report_pdf(*, school: dict[str, Any], report: dict[str, Any], period_type: str, report_label: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=13 * mm, rightMargin=13 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=periodic_title(report["profile"], period_type))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#153E75"), alignment=TA_CENTER, spaceAfter=7)
    school_style = ParagraphStyle("School", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#101828"), alignment=TA_LEFT)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=8.2, leading=10, textColor=colors.HexColor("#475467"))
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.6, leading=11, textColor=colors.HexColor("#344054"))
    center = ParagraphStyle("Center", parent=body_style, alignment=TA_CENTER)
    right = ParagraphStyle("Right", parent=body_style, alignment=TA_RIGHT)
    strong = ParagraphStyle("Strong", parent=body_style, fontName="Helvetica-Bold")
    story = []
    logo = logo_stream(school)
    if logo:
        try:
            story.append(Image(logo, width=19 * mm, height=19 * mm)); story.append(Spacer(1, 2 * mm))
        except Exception:
            pass
    story.append(Paragraph(escape(school.get("name") or "École"), school_style))
    contact = " · ".join(x for x in [school.get("address"), school.get("phone")] if x)
    if contact:
        story.append(Paragraph(escape(contact), meta_style))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(escape(periodic_title(report["profile"], period_type)), title_style))
    meta = Table([[Paragraph(f"<b>RAPPORT N° :</b> {escape(report_label)}", meta_style),
                   Paragraph(f"<b>Période :</b> {escape(period_display(report['start_date'], report['end_date'], period_type))}", meta_style)]], colWidths=[85 * mm, 85 * mm])
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(meta); story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(escape(report["profile"].get("intro") or "Mouvements financiers de la période."), body_style)); story.append(Spacer(1, 4 * mm))
    data = [[Paragraph("N°", strong), Paragraph("NOMS ET POST-NOMS", strong), Paragraph("CLASSE", strong), Paragraph("OBSERVATION", strong), Paragraph("FC", strong), Paragraph("USD", strong)]]
    for idx, row in enumerate(report["rows"], 1):
        data.append([Paragraph(str(idx), center), Paragraph(escape(_name(row)), body_style), Paragraph(escape(row.get("class_label") or "—"), body_style),
                     Paragraph(escape(str(row.get("observation") or "Paiement")), body_style),
                     Paragraph(_money(row["amount"]) if row["currency"] == "CDF" else "", right), Paragraph(_money(row["amount"]) if row["currency"] == "USD" else "", right)])
    data.append(["", Paragraph("TOTAL", strong), "", "", Paragraph(_money(report["totals"].get("CDF", 0)), right), Paragraph(_money(report["totals"].get("USD", 0)), right)])
    table = Table(data, colWidths=[9 * mm, 58 * mm, 31 * mm, 39 * mm, 22 * mm, 20 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2FF")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#153E75")),
                               ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D0D5DD")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F9FAFB")]), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F4F7")),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("ALIGN", (4, 1), (-1, -1), "RIGHT")]))
    story.append(table); story.append(Spacer(1, 12 * mm))
    signature = Table([[Paragraph("Visa / cachet de l’école", meta_style), Paragraph("Signature du responsable financier", meta_style)], ["", ""]],
                      colWidths=[85 * mm, 85 * mm], rowHeights=[5 * mm, 15 * mm])
    signature.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, 1), (0, 1), 0.4, colors.HexColor("#98A2B3")),
                                   ("LINEABOVE", (1, 1), (1, 1), 0.4, colors.HexColor("#98A2B3"))]))
    story.append(signature); story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Généré par EduSync", center))
    doc.build(story)
    return buf.getvalue()


def periodic_report_xlsx(*, school: dict[str, Any], report: dict[str, Any], period_type: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = "Rapport"; blue = "175CD3"
    ws.merge_cells("A1:G1"); ws["A1"] = school.get("name") or "École"; ws["A1"].font = Font(size=15, bold=True)
    ws.merge_cells("A2:G2"); ws["A2"] = periodic_title(report["profile"], period_type); ws["A2"].font = Font(size=12, bold=True, color=blue)
    ws.merge_cells("A3:G3"); ws["A3"] = period_display(report["start_date"], report["end_date"], period_type); ws["A3"].font = Font(italic=True, color="667085")
    ws.append(["N°", "Date", "Noms et post-noms", "Classe", "Observation", "FC", "USD"])
    for c in ws[4]:
        c.fill = PatternFill("solid", fgColor=blue); c.font = Font(bold=True, color="FFFFFF"); c.alignment = Alignment(horizontal="center")
    for i, r in enumerate(report["rows"], 1):
        amt = float(Decimal(r["amount"]))
        ws.append([i, fr_date(r["paid_day"]), _name(r), r.get("class_label") or "", r["observation"], amt if r["currency"] == "CDF" else None, amt if r["currency"] == "USD" else None])
    ws.append([None, None, "TOTAL", None, None, float(Decimal(report["totals"].get("CDF", "0"))), float(Decimal(report["totals"].get("USD", "0")))])
    thin = Side(style="thin", color="D0D5DD")
    for row in ws.iter_rows(min_row=5, max_row=ws.max_row):
        for c in row:
            c.border = Border(bottom=thin); c.alignment = Alignment(vertical="center", wrap_text=True)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True); c.fill = PatternFill("solid", fgColor="F2F4F7")
    for row in range(5, ws.max_row + 1):
        ws[f"F{row}"].number_format = "#,##0.00"; ws[f"G{row}"].number_format = "#,##0.00"
    for idx, width in enumerate([8, 14, 34, 24, 28, 16, 14], 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A5"; ws.sheet_view.showGridLines = False; ws.page_setup.orientation = "landscape"
    neutralize_formulas(wb); out = BytesIO(); wb.save(out); return out.getvalue()   # formula injection guard (D14)


def student_account_pdf(*, school: dict[str, Any], account: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    st = account["student"]; buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4); width, height = A4; left = 15 * mm; right = width - 15 * mm; y = height - 16 * mm
    cur_label = {"CDF": "FC", "USD": "USD"}
    c.setFont("Helvetica-Bold", 15); c.drawString(left, y, school.get("name") or "École"); y -= 7 * mm
    c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "RELEVÉ DU COMPTE ÉLÈVE"); y -= 6 * mm
    c.setFont("Helvetica", 8); c.drawString(left, y, f"{_name(st)} · {st.get('matricule') or '—'} · {st.get('section_label') or '—'} · {st.get('class_label') or '—'} · {st.get('year_label') or ''}"); y -= 9 * mm
    c.setFont("Helvetica-Bold", 9); c.drawString(left, y, "Synthèse"); y -= 5 * mm; c.setFont("Helvetica", 8.5)
    for row in account["summary"]:
        c.drawString(left + 4 * mm, y, f"{cur_label.get(row['currency'], row['currency'])} · Attendu {_money(row['net_expected'])} · Payé/imputé {_money(row['paid'])} · Reste {_money(row['balance'])} · {row['recovery_rate']:.1f}%"); y -= 5 * mm
    y -= 5 * mm; c.setFont("Helvetica-Bold", 9); c.drawString(left, y, "Frais et soldes"); y -= 5 * mm
    c.setFont("Helvetica-Bold", 7.5)
    for label, x in (("Frais", left), ("Devise", 95 * mm), ("Net", 120 * mm), ("Payé", 145 * mm), ("Reste", 172 * mm)):
        c.drawString(x, y, label)
    y -= 4 * mm; c.setFont("Helvetica", 7.5)
    for row in account["charges"]:
        if y < 32 * mm:
            c.showPage(); y = height - 18 * mm; c.setFont("Helvetica", 7.5)
        c.drawString(left, y, str(row["label"])[:42]); c.drawString(95 * mm, y, cur_label.get(row["currency"], row["currency"]))
        c.drawRightString(140 * mm, y, _money(row["net_amount"])); c.drawRightString(168 * mm, y, _money(row["paid"])); c.drawRightString(right, y, _money(row["balance"])); y -= 4.5 * mm
    y -= 5 * mm; c.setFont("Helvetica-Bold", 9); c.drawString(left, y, "Derniers paiements"); y -= 5 * mm; c.setFont("Helvetica", 7.5)
    for row in account["payments"][:30]:
        if y < 24 * mm:
            c.showPage(); y = height - 18 * mm; c.setFont("Helvetica", 7.5)
        at = row.get("paid_at")
        c.drawString(left, y, f"{row.get('receipt_no') or '—'} · {at.strftime('%Y-%m-%d') if hasattr(at, 'strftime') else str(at)[:10]} · {row.get('mode') or '—'} · {row['status']}")
        c.drawRightString(right, y, f"{_money(row['amount'])} {cur_label.get(row['currency'], row['currency'])}"); y -= 4.5 * mm
    c.setFont("Helvetica-Oblique", 6.5); c.drawCentredString(width / 2, 10 * mm, "Relevé généré par EduSync · FC et USD restent séparés")
    c.showPage(); c.save(); return buf.getvalue()
