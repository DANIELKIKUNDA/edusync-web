"""PDF of the weekly / monthly report (owner, 2026-11-19): the letter first (same sentences as the e-mail), then the
recovery by class of the reader's scope. Same visual identity as the direction recovery report."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from edusync.modules.finance_recovery.application.direction_report_document import BLEU, CEL, ENT, FOND, GRIS, PETIT, T1, T2, TRAIT, TX
from edusync.modules.finance_recovery.domain.digest import Digest, money, paragraphs, pct, title


def digest_pdf(*, digest: Digest, greeting: str, classes: list[dict[str, Any]], signature: str) -> bytes:
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=title(digest), author="EduSync")
    story: list[Any] = [Paragraph(escape(title(digest)), T1), Spacer(1, 3 * mm),
                        Paragraph(escape(digest.scope_label.capitalize() if digest.scope_label else "Toute l’école"), PETIT), Spacer(1, 5 * mm),
                        Paragraph(escape(greeting), TX)]
    for heading, text in paragraphs(digest):
        story.append(Paragraph((f"<b>{escape(heading)} :</b> " if heading else "") + escape(text), TX))
    story += [Spacer(1, 2 * mm), Paragraph(escape(signature), TX)]
    rows = [r for r in classes if Decimal(str(r.get("expected") or 0)) > 0]
    if rows:
        story += [Spacer(1, 4 * mm), Paragraph("Recouvrement par classe depuis la rentrée", T2)]
        data = [[Paragraph(h, ENT) for h in ("Classe", "Élèves", "Attendu", "Rentré", "Reste", "Taux")]]
        for r in sorted(rows, key=lambda x: Decimal(str(x.get("recovery_rate") or 0))):
            data.append([Paragraph(escape(str(r.get("class_label") or r.get("label") or "")), CEL), str(r.get("debtors") or 0),
                         money(r.get("expected"), digest.currency), money(r.get("regularized_total"), digest.currency),
                         money(r.get("remaining"), digest.currency), pct(r.get("recovery_rate"))])
        t = Table(data, colWidths=[44 * mm, 16 * mm, 30 * mm, 30 * mm, 30 * mm, 18 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLEU), ("GRID", (0, 0), (-1, -1), .4, TRAIT),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FOND]), ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                               ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TEXTCOLOR", (1, 1), (-1, -1), GRIS)]))
        story.append(t)
    story += [Spacer(1, 4 * mm), Paragraph("Rapport produit automatiquement par EduSync à partir des encaissements, des inscriptions "
                                           "et des mouvements d’élèves enregistrés. Les montants sont nets des annulations.", PETIT)]
    doc.build(story)
    return out.getvalue()
