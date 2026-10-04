from __future__ import annotations

from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
from io import BytesIO
from typing import Iterable


def build_staff_register_xlsx(rows: Iterable[dict], *, school_name: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    data=list(rows)
    wb=Workbook();ws=wb.active;ws.title="Personnel"
    ws.merge_cells("A1:I1");ws["A1"]=f"{school_name} — Registre du personnel";ws["A1"].font=Font(size=16,bold=True);ws["A1"].alignment=Alignment(horizontal="center")
    headers=["Matricule","Nom complet","Catégorie","Statut","Téléphone","Qualification","Fonction principale","Périmètre","Compte lié"]
    for i,h in enumerate(headers,1):
        c=ws.cell(3,i,h);c.font=Font(bold=True,color="FFFFFF");c.fill=PatternFill("solid",fgColor="1F4E78");c.alignment=Alignment(horizontal="center")
    for r_idx,item in enumerate(data,4):
        assignments=item.get("assignments") or []
        primary=next((a for a in assignments if a.get("is_primary")), assignments[0] if assignments else {})
        full=" ".join(str(x) for x in (item.get("last_name"),item.get("middle_name"),item.get("first_name")) if x)
        vals=[item.get("employee_no"),full,item.get("category"),item.get("status"),item.get("phone") or "",item.get("qualification") or "",primary.get("function_label") or "",primary.get("scope_value") or "École", "Oui" if item.get("has_linked_access") else "Non"]
        for c_idx,val in enumerate(vals,1): ws.cell(r_idx,c_idx,val)
    widths=[16,30,18,15,18,24,28,20,14]
    for i,w in enumerate(widths,1): ws.column_dimensions[get_column_letter(i)].width=w
    ws.freeze_panes="A4";ws.auto_filter.ref=f"A3:I{max(3,3+len(data))}"
    ws.sheet_view.showGridLines=False
    neutralize_formulas(wb);out=BytesIO();wb.save(out);return out.getvalue()


def build_staff_register_pdf(rows: Iterable[dict], *, school_name: str, title: str="Registre du personnel") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    data=list(rows);buf=BytesIO();doc=SimpleDocTemplate(buf,pagesize=landscape(A4),leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet();story=[Paragraph(f"<b>{school_name}</b>",styles["Title"]),Paragraph(title,styles["Heading2"]),Spacer(1,5*mm)]
    table_data=[["Matricule","Nom complet","Catégorie","Statut","Téléphone","Fonction","Périmètre","Compte"]]
    for item in data:
        assignments=item.get("assignments") or [];primary=next((a for a in assignments if a.get("is_primary")), assignments[0] if assignments else {})
        full=" ".join(str(x) for x in (item.get("last_name"),item.get("middle_name"),item.get("first_name")) if x)
        table_data.append([item.get("employee_no",""),full,item.get("category",""),item.get("status",""),item.get("phone") or "",primary.get("function_label") or "",primary.get("scope_value") or "École","Oui" if item.get("has_linked_access") else "Non"])
    t=Table(table_data,repeatRows=1,colWidths=[22*mm,43*mm,27*mm,22*mm,28*mm,42*mm,30*mm,18*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("ALIGN",(0,0),(-1,0),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E2F3")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F7F9FC")]),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.append(t);doc.build(story);return buf.getvalue()


def build_staff_profile_pdf(item: dict, *, school_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf=BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm);styles=getSampleStyleSheet()
    full=" ".join(str(x) for x in (item.get("last_name"),item.get("middle_name"),item.get("first_name")) if x)
    story=[Paragraph(f"<b>{school_name}</b>",styles["Title"]),Paragraph("Fiche du personnel",styles["Heading2"]),Spacer(1,4*mm)]
    info=[["Matricule",item.get("employee_no",""),"Nom",full],["Catégorie",item.get("category",""),"Statut",item.get("status","")],["Téléphone",item.get("phone") or "—","E-mail",item.get("email") or "—"],["Qualification",item.get("qualification") or "—","Spécialité",item.get("specialty") or "—"],["Engagement",str(item.get("hire_date") or "—"),"Sortie",str(item.get("exit_date") or "—")]]
    t=Table(info,colWidths=[30*mm,55*mm,30*mm,55*mm]);t.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EDF3FF")),("BACKGROUND",(2,0),(2,-1),colors.HexColor("#EDF3FF")),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D8DFEA")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),6)]));story.extend([t,Spacer(1,6*mm),Paragraph("Affectations",styles["Heading3"])])
    adata=[["Fonction","Périmètre","Titulariat","Début","Fin"]]
    for a in item.get("assignments") or []: adata.append([a.get("function_label") or "",a.get("scope_value") or "École",a.get("titular_class_label") or ("Oui" if a.get("is_titular") else "—"),str(a.get("start_date") or ""),str(a.get("end_date") or "—")])
    at=Table(adata,repeatRows=1,colWidths=[48*mm,35*mm,38*mm,25*mm,25*mm]);at.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D8DFEA")),("FONTSIZE",(0,0),(-1,-1),8),("PADDING",(0,0),(-1,-1),5)]));story.append(at);doc.build(story);return buf.getvalue()
