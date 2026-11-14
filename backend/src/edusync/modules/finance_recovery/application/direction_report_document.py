"""PDF of the direction recovery report (14/11/2026). Plain, human wording for the school's hierarchy: no technical terms.
Layout validated by the owner on the October 2026 report: key figures, summary, sections, classes, analysis, annexes, visa."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import CondPageBreak, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BLEU = colors.HexColor("#123A8C"); BLEU2 = colors.HexColor("#175CD3"); FOND = colors.HexColor("#F2F5FB")
GRIS = colors.HexColor("#475467"); TRAIT = colors.HexColor("#D0D5DD"); VERT = colors.HexColor("#067647")
ROUGE = colors.HexColor("#B42318"); ORANGE = colors.HexColor("#B54708"); ENCRE = colors.HexColor("#1D2939")
NBSP = " "


def _st(name: str, **k: Any) -> ParagraphStyle:
    return ParagraphStyle(name, fontName=k.pop("fontName", "Helvetica"), **k)


T1 = _st("t1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=BLEU)
T2 = _st("t2", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=BLEU, spaceBefore=8, spaceAfter=6)
TX = _st("tx", fontSize=10, leading=14.5, textColor=ENCRE, spaceAfter=6)
PETIT = _st("pt", fontSize=8.5, leading=11.5, textColor=GRIS)
CEL = _st("cel", fontSize=8.5, leading=10.5)
ENT = _st("ent", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white, alignment=1)
PUCE = _st("puce", parent=TX, leftIndent=12, firstLineIndent=-10, spaceAfter=5)


def _e(v: Any) -> str:
    return escape(str(v or ""))


def _money(v: Any, currency: str) -> str:
    n = f"{Decimal(str(v or 0)):,.0f}".replace(",", NBSP)
    return f"{n}{NBSP}{'FC' if currency == 'CDF' else currency}"


def _pct(v: Any) -> str:
    return f"{Decimal(str(v or 0)):.1f}".replace(".", ",") + f"{NBSP}%"


def _date(d: Any) -> str:
    return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else (str(d) if d else "–")


def _liste(xs: list[str]) -> str:
    return ", ".join(xs[:-1]) + " et " + xs[-1] if len(xs) > 1 else (xs[0] if xs else "")


def _table(data: list, widths: list, align: list = (), total: bool = False, zebra: bool = True) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), BLEU), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5), ("LINEBELOW", (0, 1), (-1, -1), 0.4, TRAIT),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    style += [("ALIGN", (c, 1), (c, -1), a) for c, a in align]
    if zebra:
        style += [("BACKGROUND", (0, i), (-1, i), FOND) for i in range(2, len(data) - (1 if total else 0), 2)]
    if total:
        style += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E4EAF6")), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
                  ("LINEABOVE", (0, -1), (-1, -1), 0.8, BLEU)]
    t.setStyle(TableStyle(style))
    return t


def _tile(title: str, value: str, detail: str, color=BLEU) -> Table:
    t = Table([[Paragraph(title, _st("k1", fontSize=8, leading=10, textColor=GRIS))],
               [Paragraph(value, _st("k2", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=color))],
               [Paragraph(detail, _st("k3", fontSize=7.5, leading=9.5, textColor=GRIS))]], colWidths=[126])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, TRAIT), ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _gauge(rate: Any, width: float = 44) -> Table:
    r = min(max(float(rate or 0) / 100, 0.0), 1.0)
    t = Table([["", ""]], colWidths=[max(0.5, width * r), max(0.5, width * (1 - r))], rowHeights=[6])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), VERT if r >= 0.75 else BLEU2 if r >= 0.6 else ORANGE),
                           ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#E4E7EC"))] +
                          [(k, (0, 0), (-1, -1), 0) for k in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]))
    return t


def _rate_color(rate: Any):
    v = float(rate or 0)
    return VERT if v >= 75 else ROUGE if v < 60 else ENCRE


def _canvas_class(school_name: str, header: str, footer: str):
    class Pages(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k); self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__)); self._startPage()

        def save(self):
            n = len(self._pages)
            for i, state in enumerate(self._pages, 1):
                self.__dict__.update(state); self._decor(i, n); super().showPage()
            super().save()

        def _decor(self, i: int, n: int):
            w, h = A4
            self.setFillColor(BLEU); self.rect(0, h - 6, w, 6, stroke=0, fill=1)
            if i > 1:
                self.setFont("Helvetica-Bold", 8.5); self.setFillColor(BLEU); self.drawString(36, h - 26, school_name)
                self.setFont("Helvetica", 8.5); self.setFillColor(GRIS); self.drawRightString(w - 36, h - 26, header)
                self.setStrokeColor(TRAIT); self.setLineWidth(0.5); self.line(36, h - 32, w - 36, h - 32)
            self.setStrokeColor(TRAIT); self.line(36, 34, w - 36, 34)
            self.setFont("Helvetica", 7.5); self.setFillColor(GRIS)
            self.drawString(36, 22, footer); self.drawRightString(w - 36, 22, f"Page {i} / {n}")
    return Pages


def direction_report_pdf(*, school: dict[str, Any], year_label: str, report: dict[str, Any]) -> bytes:
    cur = report["currency"]; m = lambda v: _money(v, cur); t = report["total"]; a = report["analysis"]
    school_name = school.get("name") or "École"; when = report["as_of_label"]; scope = report["scope_label"]
    story: list = [Spacer(1, 6), Paragraph(_e(school_name), _st("ecole", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=GRIS)),
                   Paragraph(f"Rapport de recouvrement<br/>{_e(report['title'])}", T1), Spacer(1, 4),
                   Paragraph(f"Année scolaire {_e(year_label)} · Situation au {when} · À l’attention de la Direction",
                             _st("sous", fontSize=10.5, leading=14, textColor=GRIS)), Spacer(1, 14)]

    if not t["concerned"]:
        story += [Paragraph("Synthèse", T2), Paragraph(f"Aucun élève n’est concerné par {_e(scope)} à cette date.", TX)]
    else:
        tiles = Table([[_tile("Taux de recouvrement", _pct(t["rate"]), "du montant attendu", VERT if t["rate"] >= 75 else BLEU2),
                        _tile("Montant encaissé", m(t["collected"]), f"sur {m(t['expected'])} attendus"),
                        _tile("Reste à recouvrer", m(t["remaining"]), f"{t['not_in_order']} élèves ne sont pas à jour", ORANGE),
                        _tile("Élèves à jour", f"{t['in_order']} sur {t['concerned']}",
                              _pct(Decimal(t["in_order"] * 100) / t["concerned"]) + " des élèves concernés")]], colWidths=[132.5] * 4)
        tiles.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6.5)]))
        story += [tiles, Spacer(1, 14), Paragraph("Synthèse", T2)]
        partial = (f" Parmi eux, <b>{t['partial']}</b> ont payé une partie seulement." if t["partial"] else
                   " Aucun paiement n’est partiel : chaque famille a soit tout réglé, soit rien encore." if t["not_in_order"] else "")
        story.append(Paragraph(
            f"Au {when}, l’école a encaissé <b>{m(t['collected'])}</b> pour {_e(scope)}, sur <b>{m(t['expected'])}</b> attendus, "
            f"soit un taux de recouvrement de <b>{_pct(t['rate'])}</b>. <b>{t['in_order']} élèves sur {t['concerned']}</b> sont à jour ; "
            f"<b>{t['not_in_order']}</b> ne le sont pas encore, ce qui représente <b>{m(t['remaining'])}</b> à recouvrer.{partial}", TX))
        secs = [s for s in report["sections"] if s["expected"] > 0]
        if len(secs) > 1:
            top = max(secs, key=lambda s: s["remaining"]); best = max(secs, key=lambda s: s["rate"]); worst = min(secs, key=lambda s: s["rate"])
            share = _pct(top["remaining"] * 100 / t["remaining"]) if t["remaining"] else _pct(0)
            txt = (f"La section <b>{_e(top['label'])}</b> concentre la plus grande part du montant restant ({m(top['remaining'])}, soit {share} du total). "
                   if top["remaining"] > 0 else "")
            if best is not worst:
                lead = "Elle affiche aussi" if txt and best is top else f"La section <b>{_e(best['label'])}</b> affiche"
                txt += f"{lead} le meilleur taux ({_pct(best['rate'])}) ; la section <b>{_e(worst['label'])}</b> a le plus faible ({_pct(worst['rate'])})."
            if txt:
                story.append(Paragraph(txt, TX))

        story.append(Paragraph("Résultats par section", T2))
        data = [[Paragraph(h, ENT) for h in ("Section", "Élèves<br/>concernés", "À jour", "Pas à jour", "Montant<br/>attendu", "Encaissé",
                                             "Reste à<br/>recouvrer", "Taux", "")]]
        for s in report["sections"] + [t]:
            data.append([Paragraph(_e(s["label"]), CEL), s["concerned"], s["in_order"], s["not_in_order"], m(s["expected"]), m(s["collected"]),
                         m(s["remaining"]), _pct(s["rate"]), _gauge(s["rate"])])
        story += [_table(data, [76, 52, 40, 48, 68, 68, 68, 40, 52], [(c, "CENTER") for c in (1, 2, 3)] + [(c, "RIGHT") for c in (4, 5, 6, 7)], total=True),
                  Spacer(1, 8)]

        if report["fees"]:
            story.append(Paragraph("Résultats par type de frais", T2))
            data = [[Paragraph(h, ENT) for h in ("Type de frais", "Élèves<br/>concernés", "À jour", "Pas à jour", "Attendu", "Encaissé", "Reste", "Taux")]]
            for f in report["fees"]:
                data.append([Paragraph(_e(f["label"]), CEL), f["concerned"], f["in_order"], f["not_in_order"], m(f["expected"]), m(f["collected"]),
                             m(f["remaining"]), _pct(f["rate"])])
            story += [_table(data, [123, 52, 40, 48, 72, 72, 72, 44], [(c, "CENTER") for c in (1, 2, 3)] + [(c, "RIGHT") for c in (4, 5, 6, 7)]),
                      Paragraph("Un même élève peut être concerné par plusieurs frais.", PETIT)]

        counts = report["exempted_counts"]
        if counts.get("ARRIVAL") or counts.get("EXEMPTION"):
            parts = []
            if counts.get("ARRIVAL"):
                parts.append(f"<b>{counts['ARRIVAL']} élèves inscrits après la date limite</b> fixée par l’école")
            if counts.get("EXEMPTION"):
                parts.append(f"<b>{counts['EXEMPTION']} élèves exonérés</b>")
            story += [Paragraph("Élèves non concernés", T2),
                      Paragraph(f"Ne sont pas concernés par {_e(scope)} : {_liste(parts)}. Ils ne sont pas comptés dans le calcul ; "
                                f"leur liste figure en annexe 2.", TX)]

        # Résultats par classe
        story += [PageBreak(), Paragraph("Résultats par classe", T2)]
        data = [[Paragraph(h, ENT) for h in ("Classe", "Élèves", "À jour", "Pas à jour", "Attendu", "Encaissé", "Reste", "Taux")]]
        section_rows, current = [], None
        for c in report["classes"]:
            if c["section_label"] != current:
                current = c["section_label"]; section_rows.append(len(data))
                data.append([Paragraph(f"<b>{_e(current)}</b>", _st("sec", fontName="Helvetica-Bold", fontSize=8.5, textColor=BLEU))] + [""] * 7)
            data.append([Paragraph(_e(c["label"]), CEL), c["concerned"], c["in_order"], c["not_in_order"], m(c["expected"]), m(c["collected"]),
                         m(c["remaining"]), _pct(c["rate"])])
        data.append(["Total", t["concerned"], t["in_order"], t["not_in_order"], m(t["expected"]), m(t["collected"]), m(t["remaining"]), _pct(t["rate"])])
        tbl = _table(data, [123, 44, 44, 52, 72, 72, 72, 44], [(c, "CENTER") for c in (1, 2, 3)] + [(c, "RIGHT") for c in (4, 5, 6, 7)], total=True, zebra=False)
        extra = [("TOPPADDING", (0, 1), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 1), (-1, -1), 1.6)]
        for i in section_rows:
            extra += [("SPAN", (0, i), (-1, i)), ("BACKGROUND", (0, i), (-1, i), FOND)]
        ci = 0
        for i in range(1, len(data) - 1):
            if i not in section_rows:
                extra.append(("TEXTCOLOR", (7, i), (7, i), _rate_color(report["classes"][ci]["rate"]))); ci += 1
        tbl.setStyle(TableStyle(extra))
        story.append(tbl)

        # Analyse
        story += [CondPageBreak(220), Paragraph("Analyse", T2)]
        full = a["full_classes"]
        story.append(Paragraph("•" + NBSP * 2 + (f"<b>{len(full)} classe{'s' if len(full) > 1 else ''} entièrement à jour</b> : {_e(_liste(full))}." if full
                                                else "Aucune classe n’est encore entièrement à jour."), PUCE))
        if a["lowest"]:
            story.append(Paragraph("•" + NBSP * 2 + "<b>Classes les plus en retard</b> (taux le plus faible) : " +
                                   _e(_liste([f"{c['label']} ({_pct(c['rate'])})" for c in a["lowest"]])) + ".", PUCE))
        if a["biggest"]:
            n = len(a["biggest"])
            story.append(Paragraph("•" + NBSP * 2 + "<b>Plus gros montants restant à recouvrer</b> : " +
                                   _e(_liste([f"{c['label']} ({m(c['remaining'])})" for c in a["biggest"]])) +
                                   (f". À elles seules, ces {n} classes représentent {m(a['biggest_sum'])}." if n > 1 else "."), PUCE))
        if t["not_in_order"]:
            w = a["without_contact"]
            story.append(Paragraph("•" + NBSP * 2 + (f"<b>{w} des {t['not_in_order']} élèves pas à jour n’ont aucun numéro de téléphone</b> "
                                                     "enregistré pour leur famille : ils ne peuvent pas être relancés par téléphone." if w else
                                                     "Tous les élèves pas à jour ont un numéro de téléphone enregistré pour leur famille."), PUCE))

        # Annexe 1
        unpaid = report["unpaid"]
        if unpaid:
            story += [PageBreak(), Paragraph(f"Annexe 1 — Élèves pas encore à jour ({len(unpaid)})", T2),
                      Paragraph("Classés par section puis par classe, avec le contact du parent ou tuteur pour les relances.", PETIT), Spacer(1, 6)]
            show_missing = (report["period_label"] is None)
            head = ("N°", "Classe", "Élève", "Parent / tuteur", "Téléphone") + (("Non réglé",) if show_missing else ()) + ("Reste dû",)
            data = [[Paragraph(h, ENT) for h in head]]
            for i, st in enumerate(unpaid, 1):
                row = [i, Paragraph(_e(st["class_label"]), CEL), Paragraph(_e(st["student_name"]), CEL),
                       Paragraph(_e(st["contact_name"]) or "<font color='#98A2B3'>non renseigné</font>", CEL), st["contact_phone"] or "–"]
                if show_missing:
                    row.append(Paragraph(_e(", ".join(st["missing"])), CEL))
                data.append(row + [m(st["remaining"])])
            data.append(["", "", "Total", "", ""] + ([""] if show_missing else []) + [m(sum((s["remaining"] for s in unpaid), Decimal(0)))])
            widths = [22, 46, 125, 106, 72, 88, 64] if show_missing else [22, 50, 165, 140, 84, 62]
            story.append(_table(data, widths, [(0, "CENTER"), (len(head) - 1, "RIGHT")], total=True))

    # Annexe 2
    ex = report["exempted"]
    if ex:
        story += [CondPageBreak(160), Spacer(1, 12), Paragraph(f"Annexe 2 — Élèves non concernés ({len(ex)})", T2),
                  Paragraph("Ces élèves ne doivent pas les frais de ce rapport à cette date et ne sont pas comptés dans le calcul.", PETIT), Spacer(1, 6)]
        data = [[Paragraph(h, ENT) for h in ("N°", "Classe", "Élève", "Inscrit le", "Motif", "Période")]]
        for i, g in enumerate(ex, 1):
            data.append([i, Paragraph(_e(g["class_label"]), CEL), Paragraph(_e(g["student_name"]), CEL), _date(g["enrolled_on"]),
                         Paragraph(_e(g["reason_label"]), CEL), Paragraph(_e(", ".join(g["periods"])), CEL)])
        story.append(_table(data, [22, 50, 170, 58, 118, 104], [(0, "CENTER"), (3, "CENTER")]))

    story += [Spacer(1, 24), Table([[f"Établi le {when}", "Visa de la Direction"], ["", ""]], colWidths=[264, 264], rowHeights=[16, 46],
                                   style=TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("TEXTCOLOR", (0, 0), (-1, -1), GRIS),
                                                     ("LINEBELOW", (1, 1), (1, 1), 0.6, TRAIT)]))]
    out = BytesIO()
    header = f"Recouvrement — {report['title']}"
    SimpleDocTemplate(out, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=44, bottomMargin=46,
                      title=f"Rapport de recouvrement — {report['title']} — {school_name}", author=school_name,
                      subject=f"Recouvrement — {report['title']}").build(
        story, canvasmaker=_canvas_class(school_name, header, f"Confidentiel — usage interne · Situation au {when}"))
    return out.getvalue()
