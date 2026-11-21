"""G-DOC-3 — cash journal and daily financial report PDFs, copied from the Desktop golden master
(app/services/documents.py::export_cash_journal_pdf and ::export_daily_financial_report_pdf). Currencies are never added
together; every amount keeps its own currency."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

CURRENCY = {"CDF": "FC", "USD": "USD"}
SOURCES = {"FONDS_ANTICIPE": "Fonds anticipé reçu", "PAIEMENT_ELEVE": "Paiement élève", "DEPENSE_JOURNALIERE": "Dépense", "REMBOURSEMENT": "Remboursement", "ANNULATION": "Annulation",
           "VENTE_ARTICLE": "Vente article", "RESTITUTION_FONDS_ANTICIPE": "Restitution fonds anticipé"}


def _money(v: Any) -> str:
    return f"{Decimal(str(v or 0)):,.2f}".replace(",", " ")


def _status(report: dict[str, Any]) -> str:
    return "Clôturée" if report.get("closed") else "Ouverte"


def cash_journal_pdf(*, school_name: str, report: dict[str, Any], title: str | None = None) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    width, height = landscape(A4)
    left, right = 12 * mm, width - 12 * mm
    y = height - 12 * mm
    day = report["day"]

    def header():
        nonlocal y
        c.setFont("Helvetica-Bold", 14); c.drawString(left, y, school_name or "École"); y -= 7 * mm
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, title or f"JOURNAL DE CAISSE — {day}"); y -= 6 * mm
        c.setFont("Helvetica", 8); c.drawString(left, y, f"Statut : {_status(report)}"); y -= 8 * mm

    header()
    c.setFont("Helvetica-Bold", 9); c.drawString(left, y, "Synthèse"); y -= 5 * mm; c.setFont("Helvetica", 8)
    for r in report.get("totals", []):
        c.drawString(left + 4 * mm, y, f"{CURRENCY.get(r['currency'], r['currency'])}  ·  Entrées {_money(r['entries'])}  ·  Sorties {_money(r['outflows'])}  ·  Solde {_money(r['net'])}")
        y -= 4.5 * mm
    y -= 4 * mm
    cols = [("Heure", left, 22 * mm), ("Sens", left + 23 * mm, 22 * mm), ("Opération", left + 46 * mm, 48 * mm), ("Montant", left + 95 * mm, 30 * mm),
            ("Devise", left + 126 * mm, 20 * mm), ("Mode", left + 147 * mm, 28 * mm), ("Référence", left + 176 * mm, 38 * mm),
            ("Détail", left + 215 * mm, 45 * mm), ("Utilisateur", left + 261 * mm, 25 * mm)]

    def table_head():
        nonlocal y
        c.setFont("Helvetica-Bold", 7)
        for name, x, _ in cols:
            c.drawString(x, y, name)
        y -= 4 * mm; c.line(left, y + 2 * mm, right, y + 2 * mm); c.setFont("Helvetica", 6.7)

    table_head()
    for op in report.get("operations", []):
        if y < 14 * mm:
            c.showPage(); y = height - 12 * mm; header(); table_head()
        at = op.get("created_at")
        vals = [at.strftime("%H:%M:%S") if hasattr(at, "strftime") else str(at or "")[11:19], "Entrée" if op.get("direction") == "ENTREE" else "Sortie",
                SOURCES.get(op.get("source"), str(op.get("source") or "").replace("_", " ").title()), _money(op.get("amount")),
                CURRENCY.get(op.get("currency"), op.get("currency")), op.get("mode") or "—", op.get("reference") or "—", op.get("reason") or "—",
                op.get("user_name") or "—"]
        for (_, x, w), val in zip(cols, vals):
            c.drawString(x, y, str(val)[:max(6, int(w / mm * 1.6))])
        y -= 4.2 * mm
    c.setFont("Helvetica-Oblique", 6.5); c.drawRightString(right, 7 * mm, "EduSync · Journal de caisse")
    c.drawString(left, 7 * mm, "Les devises ne sont jamais additionnées entre elles : FC et USD restent séparés.")
    c.showPage(); c.save()
    return buf.getvalue()


def _amount(v: Any, currency: str | None) -> str:
    """« 1 110 000 FC » — French grouping, no useless decimals (« 12,50 USD » only when there are cents)."""
    d = Decimal(str(v or 0))
    txt = f"{d:,.0f}" if d == d.to_integral() else f"{d:,.2f}"
    return txt.replace(",", " ").replace(".", ",") + " " + CURRENCY.get(currency or "", currency or "")


def daily_report_pdf(*, school_name: str, report: dict[str, Any], prepared_by: str | None = None) -> bytes:
    """Management-grade daily report (owner, 2026-11-21: « la justification n'est pas entière » and « est-ce que la mise
    en page est très professionnelle ? »). Real tables, the whole justification written by the cashier (wrapped, never
    cut), French amounts, the day status, totals that explain the summary and a visa block. FC and USD never added."""
    from datetime import datetime
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    blue, ink, grey, line, soft = (colors.HexColor(x) for x in ("#123A8C", "#1D2939", "#475467", "#D0D5DD", "#F2F5FB"))

    def st(name: str, **k: Any) -> ParagraphStyle:
        return ParagraphStyle(name, fontName=k.pop("fontName", "Helvetica"), textColor=k.pop("textColor", ink), **k)

    H1 = st("h1", fontName="Helvetica-Bold", fontSize=15, leading=19)
    H2 = st("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=blue)
    SEC = st("sec", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=blue, spaceBefore=8, spaceAfter=4)
    TXT = st("txt", fontSize=8.5, leading=11.5)
    CELL = st("cell", fontSize=8, leading=10.2)
    HEAD = st("head", fontName="Helvetica-Bold", fontSize=7.8, leading=9.5, textColor=colors.white)
    RIGHT = st("right", fontSize=8, leading=10.2, alignment=2)
    BOLDR = st("boldr", fontName="Helvetica-Bold", fontSize=8.3, leading=10.5, alignment=2)
    SMALL = st("small", fontSize=7.2, leading=9, textColor=grey)
    WARN = st("warn", fontSize=8, leading=10.5, textColor=colors.HexColor("#B54708"))

    def fr_day(v: str) -> str:
        try:
            y, m, d = str(v).split("-")[:3]
            return f"{d[:2]}/{m}/{y}"
        except Exception:
            return str(v)

    def p(v: Any, style: ParagraphStyle = CELL) -> Paragraph:
        return Paragraph(escape(str(v if v not in (None, "") else "—")), style)

    def table(rows: list[list[Any]], widths: list[float], *, total_row: bool = False) -> Table:
        t = Table(rows, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), blue), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("GRID", (0, 0), (-1, -1), .35, line), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
                 ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if total_row:
            style += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EEF9")), ("LINEABOVE", (0, -1), (-1, -1), .9, blue),
                      ("SPAN", (0, -1), (-1, -1))]
        t.setStyle(TableStyle(style))
        return t

    closed = bool(report.get("closed"))
    status = "Clôturée" if closed else "Ouverte"
    day = fr_day(report["day"])
    totals = report.get("totals") or [{"currency": "CDF", "entries": "0", "outflows": "0", "net": "0"}]
    ops = report.get("operations", [])
    W = A4[0] - 28 * mm

    story: list[Any] = [Paragraph(escape(school_name or "École"), H1),
                        Paragraph(f"RAPPORT FINANCIER JOURNALIER — {day}", H2), Spacer(1, 3 * mm)]
    info = Table([[p("Journée", SMALL), p("Statut", SMALL), p("Caisses de la journée", SMALL), p("Encore ouvertes", SMALL)],
                  [p(day, TXT), p(status, TXT), p(report.get("sessions", 0), TXT), p(report.get("open_sessions", 0), TXT)]],
                 colWidths=[W / 4] * 4)
    info.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, line), ("BACKGROUND", (0, 0), (-1, -1), soft),
                              ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story.append(info)
    if not closed:
        story += [Spacer(1, 2.5 * mm), Paragraph("Journée non clôturée : les chiffres sont provisoires tant que toutes les "
                                                 "caisses ne sont pas fermées.", WARN)]

    story.append(Paragraph("Synthèse par devise", SEC))
    rows = [[p(h, HEAD) for h in ("Devise", "Entrées", "Sorties", "Solde net", "État")]]
    for r in totals:
        cur = r["currency"]
        rows.append([p(CURRENCY.get(cur, cur)), p(_amount(r["entries"], cur), RIGHT), p(_amount(r["outflows"], cur), RIGHT),
                     p(_amount(r["net"], cur), BOLDR), p(status)])
    story.append(table(rows, [W * .14, W * .24, W * .24, W * .24, W * .14]))

    story.append(Paragraph("Ventilation par origine", SEC))
    details = report.get("details", [])
    if details:
        rows = [[p(h, HEAD) for h in ("Origine", "Sens", "Devise", "Montant")]]
        for r in details:
            rows.append([p(SOURCES.get(r["source"], r["source"])), p("Entrée" if r["direction"] == "ENTREE" else "Sortie"),
                         p(CURRENCY.get(r["currency"], r["currency"])), p(_amount(r["amount"], r["currency"]), RIGHT)])
        story.append(table(rows, [W * .46, W * .16, W * .14, W * .24]))
    else:
        story.append(p("Aucun mouvement financier pour cette journée.", TXT))

    def ledger(direction: str, heading: str) -> None:
        story.append(Paragraph(heading, SEC))
        items = [op for op in ops if op.get("direction") == direction]
        if not items:
            story.append(p("Aucun mouvement.", TXT))
            return
        rows = [[p(h, HEAD) for h in ("Heure", "Opération", "Élève / justification", "Référence", "Montant", "Opérateur")]]
        for op in items:
            at = op.get("created_at")
            hour = at.strftime("%H:%M") if hasattr(at, "strftime") else str(at or "")[11:16]
            why = " — ".join(str(v) for v in (op.get("party"), op.get("reason")) if v) or "—"
            rows.append([p(hour), p(SOURCES.get(op.get("source"), str(op.get("source") or "").replace("_", " ").title())), p(why),
                         p(op.get("reference")), p(_amount(op.get("amount"), op.get("currency")), RIGHT), p(op.get("user_name"))])
        sums: dict[Any, Decimal] = {}
        for op in items:
            sums[op.get("currency")] = sums.get(op.get("currency"), Decimal("0")) + Decimal(str(op.get("amount") or 0))
        total = " · ".join(_amount(v, k) for k, v in sums.items())
        rows.append([Paragraph(f"TOTAL {heading.upper()} : {escape(total)}", BOLDR), "", "", "", "", ""])
        story.append(table(rows, [W * .08, W * .14, W * .36, W * .14, W * .15, W * .13], total_row=True))

    ledger("ENTREE", "Détail des entrées")
    ledger("SORTIE", "Détail des sorties")

    # Owner, 2026-11-21: « pourquoi établi par, le système ne connaît pas celui qui l'a établi ? » — the system writes
    # who generated the report and which cashiers worked that day; only the signatures stay handwritten.
    cashiers = sorted({str(op.get("user_name")) for op in ops if op.get("user_name")})
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    made = [Paragraph("<b>Établi par</b>", CELL), p(f"{prepared_by or '—'}, le {stamp}", TXT),
            p("Caissier(s) de la journée : " + (", ".join(cashiers) if cashiers else "—"), SMALL)]
    sig = Table([[made, [Paragraph("<b>Vérifié par</b>", CELL), p("Responsable financier", SMALL)],
                  [Paragraph("<b>Visa de la direction</b>", CELL), p("Promoteur ou direction", SMALL)]],
                 [Spacer(1, 14 * mm), "", ""], [p("Signature", SMALL), p("Nom, date et signature", SMALL), p("Nom, date et signature", SMALL)]],
                colWidths=[W / 3] * 3)
    sig.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, line), ("INNERGRID", (0, 0), (-1, -1), .35, line),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 6 * mm), KeepTogether([Paragraph("Visas", SEC), sig])]
    if report.get("closed_at"):
        story += [Spacer(1, 2 * mm), p("Clôture de journée enregistrée.", SMALL)]

    def on_page(cv: Any, doc: Any) -> None:
        cv.saveState(); cv.setFont("Helvetica", 6.8); cv.setFillColor(grey)
        cv.drawString(14 * mm, 9 * mm, f"Généré par EduSync le {stamp} · FC et USD ne sont jamais additionnés.")
        cv.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {doc.page}")
        cv.setStrokeColor(line); cv.line(14 * mm, 12 * mm, A4[0] - 14 * mm, 12 * mm); cv.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
                            title=f"Rapport financier journalier — {day}", author="EduSync")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def advance_receipt_pdf(*, school: dict[str, Any], fund: dict[str, Any]) -> bytes:
    """N3-D — Desktop export_advance_receipt_pdf (A5): amount received, already imputed, available."""
    from reportlab.lib.pagesizes import A5
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    width, height = A5
    y = height - 16 * mm
    cur = CURRENCY.get(fund["currency"], fund["currency"])
    c.setFont("Helvetica-Bold", 14); c.drawString(14 * mm, y, school.get("name") or "École"); y -= 7 * mm
    c.setFont("Helvetica", 8); c.drawString(14 * mm, y, " · ".join(x for x in [school.get("address"), school.get("phone")] if x)); y -= 9 * mm
    c.setFont("Helvetica-Bold", 13); c.drawString(14 * mm, y, f"REÇU FONDS ANTICIPÉ {fund.get('receipt_number') or ''}"); y -= 9 * mm
    name = " ".join(x for x in [fund.get("last_name"), fund.get("middle_name"), fund.get("first_name")] if x)
    at = fund.get("received_at")
    lines = [("Élève", name), ("Matricule", fund.get("matricule") or "—"), ("Classe", fund.get("class_label") or "—"),
             ("Montant reçu", f"{_money(fund['amount'])} {cur}"), ("Déjà imputé", f"{_money(fund.get('allocated_amount'))} {cur}"),
             ("Disponible", f"{_money(fund.get('available_amount'))} {cur}"), ("Mode", fund.get("mode") or "—"), ("Référence", fund.get("reference") or "—"),
             ("Caissier", fund.get("cashier") or "—"), ("Date", at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(at, "strftime") else str(at or "")[:19]),
             ("Statut", fund.get("status") or "—")]
    for label, value in lines:
        c.setFont("Helvetica-Bold", 9); c.drawString(14 * mm, y, f"{label} :"); c.setFont("Helvetica", 9); c.drawString(47 * mm, y, str(value)); y -= 5.5 * mm
    y -= 6 * mm; c.setFont("Helvetica-Oblique", 7)
    c.drawString(14 * mm, y, "Fonds anticipé : montant reçu avant imputation, distinct d'un plan de paiement anticipé.")
    c.showPage(); c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- 2026-10-25 — « voir les caisses passées et exporter la caisse »
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas

_HEAD = PatternFill("solid", fgColor="1F4E78")


def _num(v: Any) -> float | None:
    return None if v is None else float(Decimal(str(v)))


def _sheet_head(ws, school_name: str, title: str, subtitle: str, headers: list[str]) -> None:
    last = get_column_letter(len(headers))
    for row, value, size in ((1, school_name or "École", 15), (2, title, 12), (3, subtitle, 10)):
        ws.merge_cells(f"A{row}:{last}{row}"); ws[f"A{row}"] = value; ws[f"A{row}"].font = Font(size=size, bold=row < 3)
        ws[f"A{row}"].alignment = Alignment(horizontal="center")
    for j, h in enumerate(headers, 1):
        c = ws.cell(5, j, h); c.font = Font(bold=True, color="FFFFFF"); c.fill = _HEAD; c.alignment = Alignment(horizontal="center", wrap_text=True)
    ws.freeze_panes = "A6"; ws.sheet_view.showGridLines = False; ws.print_title_rows = "1:5"; ws.page_setup.orientation = "landscape"


def session_journal_xlsx(*, school_name: str, session: dict[str, Any], cashier: str, operations: list[dict[str, Any]]) -> bytes:
    """One cash session: every movement, then the summary per currency (never added together)."""
    wb = Workbook(); ws = wb.active; ws.title = "Journal de caisse"
    headers = ["Heure", "Sens", "Opération", "Élève / libellé", "Montant", "Devise", "Mode", "Référence", "Motif", "Contre-opéré"]
    sub = f"Caissier : {cashier} · Journée {session.get('business_date')} · {'Clôturée' if session.get('status') == 'CLOSED' else 'Ouverte'}"
    _sheet_head(ws, school_name, "JOURNAL DE CAISSE", sub, headers)
    i = 6
    for op in operations:
        at = op.get("created_at")
        vals = [at.strftime("%H:%M:%S") if hasattr(at, "strftime") else str(at or "")[11:19], "Entrée" if op.get("direction") == "ENTREE" else "Sortie",
                SOURCES.get(op.get("source"), str(op.get("source") or "").replace("_", " ").title()), op.get("party") or "",
                _num(op.get("amount")), CURRENCY.get(op.get("currency"), op.get("currency")), op.get("mode") or "",
                op.get("reference") or "", op.get("reason") or "", "Oui" if op.get("reversed") else ""]
        for j, v in enumerate(vals, 1):
            ws.cell(i, j, v)
        ws.cell(i, 5).number_format = "#,##0.00"; i += 1
    i += 1
    ws.cell(i, 1, "Synthèse").font = Font(bold=True); i += 1
    for j, h in enumerate(["Devise", "Fond initial", "Entrées", "Dépenses", "Contre-opérations", "Solde théorique", "Compté", "Écart"], 1):
        c = ws.cell(i, j, h); c.font = Font(bold=True, color="FFFFFF"); c.fill = _HEAD
    for cur in ("CDF", "USD"):
        x = session.get(cur.lower()) or {}; i += 1
        vals = [CURRENCY[cur], x.get("opening"), x.get("receipts"), x.get("expenses"), x.get("reversals"), x.get("expected_cash"), x.get("counted"), x.get("variance")]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(i, j, _num(v) if j > 1 else v)
            if j > 1:
                cell.number_format = "#,##0.00"
    for j, w in enumerate([10, 9, 22, 28, 14, 8, 14, 16, 30, 12], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.auto_filter.ref = f"A5:J{max(5, 5 + len(operations))}"
    neutralize_formulas(wb); out = BytesIO(); wb.save(out); return out.getvalue()


def sessions_xlsx(*, school_name: str, start: str, end: str, sessions: list[dict[str, Any]]) -> bytes:
    """Cash sessions of a period, one line each, CDF and USD in separate columns."""
    wb = Workbook(); ws = wb.active; ws.title = "Caisses"
    headers = ["Journée", "Caissier", "Ouverture", "Clôture", "Statut", "Entrées FC", "Sorties FC", "Solde FC", "Compté FC", "Écart FC",
               "Entrées USD", "Sorties USD", "Solde USD", "Compté USD", "Écart USD"]
    _sheet_head(ws, school_name, "HISTORIQUE DES CAISSES", f"Du {start} au {end}", headers)
    for i, s_ in enumerate(sessions, 6):
        row: list[Any] = [str(s_.get("business_date")), s_.get("cashier_name") or "—", str(s_.get("opened_at") or "")[11:16], str(s_.get("closed_at") or "")[11:16],
                          "Clôturée" if s_.get("status") == "CLOSED" else "Ouverte"]
        for cur in ("cdf", "usd"):
            x = s_.get(cur) or {}
            out_ = Decimal(str(x.get("expenses") or 0)) + Decimal(str(x.get("reversals") or 0))
            row += [_num(x.get("receipts")), _num(out_), _num(x.get("expected_cash")), _num(x.get("counted")), _num(x.get("variance"))]
        for j, v in enumerate(row, 1):
            cell = ws.cell(i, j, v)
            if j > 5:
                cell.number_format = "#,##0.00"
    for j in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 22 if j == 2 else 13
    ws.auto_filter.ref = f"A5:{get_column_letter(len(headers))}{max(5, 5 + len(sessions))}"
    neutralize_formulas(wb); out = BytesIO(); wb.save(out); return out.getvalue()
