from __future__ import annotations

from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any


def _school_meta(school_name: str | None = None, school: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(school or {})
    if school_name and not out.get("name"):
        out["name"] = school_name
    out.setdefault("name", "EduSync École")
    return out


def _contact_lines(school: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    address = " - ".join(str(v) for v in (school.get("address"), school.get("city"), school.get("province")) if v)
    if address:
        lines.append(address)
    contacts = " | ".join(
        part for part in (
            f"Tél. : {school.get('phone')}" if school.get("phone") else "",
            f"E-mail : {school.get('email')}" if school.get("email") else "",
        ) if part
    )
    if contacts:
        lines.append(contacts)
    return lines


def _logo_path(school: dict[str, Any]):
    # Logo bytes come only from this school's object storage (never from a server file path).
    from edusync.modules.documents.application.object_store import logo_stream
    return logo_stream(school)


def _column_width(header: object, values: list[object]) -> float:
    label = str(header or "").strip().lower()
    fixed = {
        "n°": 7, "no": 7, "sexe": 8, "m/f": 8, "statut": 14,
        "matricule": 16, "année": 15, "section": 14, "classe": 18,
        "date naissance": 15, "lieu naissance": 20, "naissance / lieu": 20,
        "téléphone": 18, "responsable": 28, "responsable / foyer": 28,
        "responsable / téléphone": 30, "famille / foyer": 28,
        "code": 16, "code famille": 16, "adresse": 30,
        "élève": 34, "élèves concernés": 34, "agent lié": 24,
        "mode financier": 24, "avantage": 22, "frais concerné": 22,
        "critère": 20, "situation": 14, "réduction": 14,
        "enfants inscrits": 14, "responsable principal": 28,
    }
    if label in fixed:
        return fixed[label]
    longest = max([len(str(header or "")), *(len(str(v or "")) for v in values)], default=10)
    return min(28, max(11, longest + 2))


def _pdf_column_weights(headers: list[str]) -> list[float]:
    weights: list[float] = []
    for header in headers:
        label = str(header or "").strip().lower()
        if label in {"n°", "no"}: weights.append(0.45)
        elif label in {"sexe", "m/f"}: weights.append(0.65)
        elif label == "matricule": weights.append(1.3)
        elif label == "année": weights.append(1.5)
        elif label in {"section", "statut", "réduction", "situation"}: weights.append(0.85)
        elif label in {"élève", "famille / foyer", "responsable", "responsable / foyer", "responsable / téléphone", "élèves concernés", "responsable principal"}: weights.append(2.0)
        elif label in {"adresse", "agent lié", "mode financier", "frais concerné", "critère", "avantage"}: weights.append(1.45)
        elif label in {"classe", "date naissance", "lieu naissance", "naissance / lieu", "téléphone"}: weights.append(1.15)
        else: weights.append(1.0)
    return weights


def export_schooling_pdf_bytes(*, school: dict[str, Any], title: str, filters: list[str], headers: list[str], rows: list[list[object]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO(); styles = getSampleStyleSheet()
    center = ParagraphStyle("schooling-center", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8, leading=10)
    heading = ParagraphStyle("schooling-title", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14, leading=17, textColor=colors.HexColor("#123A8C"))
    cell = ParagraphStyle("schooling-cell", parent=center, fontSize=7.0, leading=8.4, textColor=colors.HexColor("#172033"))
    head = ParagraphStyle("schooling-head", parent=center, fontName="Helvetica-Bold", fontSize=7.1, leading=8.5, textColor=colors.white)
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=9*mm, rightMargin=9*mm, topMargin=9*mm, bottomMargin=9*mm)
    identity = Paragraph("<b>%s</b><br/>%s" % (str(school.get("name") or "EduSync École"), "<br/>".join(_contact_lines(school))), center)
    logo = _logo_path(school)
    if logo:
        try: brand = Table([[Image(logo, width=18*mm, height=18*mm), identity]], colWidths=[22*mm, landscape(A4)[0]-40*mm])
        except Exception: brand = Table([[identity]], colWidths=[landscape(A4)[0]-18*mm])
    else:
        brand = Table([[identity]], colWidths=[landscape(A4)[0]-18*mm])
    brand.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,0),(-1,-1),0.4,colors.HexColor("#D0D5DD")),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    context = " | ".join([*filters, f"Édité le {datetime.now():%d/%m/%Y %H:%M}", f"Total : {len(rows)}"])
    story=[brand,Spacer(1,3*mm),Paragraph(title,heading),Paragraph(context,center),Spacer(1,5*mm)]
    import html
    def esc(v: object) -> str: return html.escape(str(v if v not in (None,"") else "—"))
    data=[[Paragraph(esc(v),head) for v in headers]]+[[Paragraph(esc(v),cell) for v in row] for row in rows]
    available=landscape(A4)[0]-18*mm; weights=_pdf_column_weights(headers); total=sum(weights) or 1
    table=Table(data,colWidths=[available*w/total for w in weights],repeatRows=1,hAlign="CENTER")
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#175CD3")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D0D5DD")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAFC")]),
        ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(table); doc.build(story); return buf.getvalue()


def export_schooling_xlsx_bytes(*, school: dict[str, Any], title: str, filters: list[str], headers: list[str], rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    wb=Workbook(); ws=wb.active; ws.title="Liste"; width=max(1,len(headers)); logo=_logo_path(school); identity_start=3 if logo else 1
    if logo:
        from openpyxl.drawing.image import Image
        try:
            img=Image(logo); img.width=54; img.height=54; ws.add_image(img,"A1")
        except Exception: identity_start=1
    for row in range(1,5): ws.row_dimensions[row].height=19
    ws.merge_cells(start_row=1,start_column=identity_start,end_row=1,end_column=width)
    c=ws.cell(1,identity_start,school.get("name") or "EduSync École"); c.font=Font(bold=True,size=15,color="123A8C"); c.alignment=Alignment(horizontal="center",vertical="center")
    ws.merge_cells(start_row=2,start_column=identity_start,end_row=2,end_column=width)
    c=ws.cell(2,identity_start," | ".join(_contact_lines(school)) or "Document officiel EduSync"); c.font=Font(size=9,color="475467"); c.alignment=Alignment(horizontal="center",vertical="center")
    ws.merge_cells(start_row=3,start_column=1,end_row=3,end_column=width); c=ws.cell(3,1,title); c.font=Font(bold=True,size=12,color="123A8C"); c.alignment=Alignment(horizontal="center",vertical="center")
    ws.merge_cells(start_row=4,start_column=1,end_row=4,end_column=width); ws.cell(4,1," | ".join([*filters,f"Édité le {datetime.now():%d/%m/%Y %H:%M}",f"Total : {len(rows)}"])).alignment=Alignment(horizontal="center",vertical="center")
    thin=Side(style="thin",color="D0D5DD")
    for col,value in enumerate(headers,start=1):
        c=ws.cell(5,col,value); c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="175CD3"); c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); c.border=Border(top=thin,bottom=thin,left=thin,right=thin)
    for ri,row in enumerate(rows,start=6):
        for col,value in enumerate(row,start=1):
            c=ws.cell(ri,col,"" if value is None else value); c.alignment=Alignment(vertical="top",wrap_text=True); c.border=Border(top=thin,bottom=thin,left=thin,right=thin)
            if ri%2==0: c.fill=PatternFill("solid",fgColor="F8FAFC")
    for col in range(1,len(headers)+1):
        vals=[r[col-1] if len(r)>=col else "" for r in rows]; ws.column_dimensions[get_column_letter(col)].width=_column_width(headers[col-1],vals)
    ws.freeze_panes="A6"; ws.auto_filter.ref=f"A5:{get_column_letter(max(1,len(headers)))}{max(5,len(rows)+5)}"; ws.sheet_view.showGridLines=False
    neutralize_formulas(wb); buf=BytesIO(); wb.save(buf); return buf.getvalue()


def _student_status_label(value: Any) -> str:
    return {'ACTIVE':'Actif','ACTIF':'Actif','ABANDON':'Abandonné','ABANDONNE':'Abandonné','TRANSFERRED':'Transféré','TRANSFERE':'Transféré','SUSPENDED':'Suspendu','SUSPENDU':'Suspendu','INACTIVE':'Inactif'}.get(str(value or ''),str(value or '—'))


def _student_rows(rows:list[dict[str,Any]]) -> list[list[object]]:
    out=[]
    for i,r in enumerate(rows,1):
        name=' '.join(str(r.get(k) or '') for k in ('last_name','middle_name','first_name')).strip()
        guardian=r.get('primary_responsible') or r.get('family_name') or '—'
        out.append([i,r.get('matricule'),name,r.get('gender') or r.get('sex') or '—',r.get('academic_year_label') or r.get('year_label') or '—',r.get('section_label') or r.get('section_name') or '—',r.get('class_label') or '—',r.get('birth_date') or '—',r.get('birth_place') or '—',guardian,r.get('family_phone') or '—',_student_status_label(r.get('status'))])
    return out


def student_directory_pdf(*, school_name:str|None=None, school:dict[str,Any]|None=None, rows:list[dict[str,Any]], filters:str|list[str]="") -> bytes:
    headers=["N°","Matricule","Élève","Sexe","Année","Section","Classe","Date naissance","Lieu naissance","Responsable / foyer","Téléphone","Statut"]
    fs=[filters] if isinstance(filters,str) and filters else list(filters or [])
    return export_schooling_pdf_bytes(school=_school_meta(school_name,school),title="LISTE DES ÉLÈVES",filters=fs,headers=headers,rows=_student_rows(rows))


def student_directory_xlsx(*, school_name:str|None=None, school:dict[str,Any]|None=None, rows:list[dict[str,Any]], filters:str|list[str]="") -> bytes:
    headers=["N°","Matricule","Élève","Sexe","Année","Section","Classe","Date naissance","Lieu naissance","Responsable / foyer","Téléphone","Statut"]
    fs=[filters] if isinstance(filters,str) and filters else list(filters or [])
    return export_schooling_xlsx_bytes(school=_school_meta(school_name,school),title="LISTE DES ÉLÈVES",filters=fs,headers=headers,rows=_student_rows(rows))


def _family_rows(rows:list[dict[str,Any]]) -> list[list[object]]:
    out=[]
    for r in rows:
        guardians=r.get('guardians') or []
        primary=next((g for g in guardians if g.get('is_primary')),None) or (guardians[0] if guardians else None)
        out.append([r.get('code'),r.get('display_name') or r.get('name'),(primary or {}).get('full_name') or r.get('primary_responsible') or 'Contact à compléter',r.get('phone') or (primary or {}).get('phone') or r.get('primary_responsible_phone') or '—',r.get('address') or '—',r.get('enrolled_children',r.get('child_count',0))])
    return out


def family_directory_pdf(*, school_name:str|None=None, school:dict[str,Any]|None=None, rows:list[dict[str,Any]], filters:str|list[str]="") -> bytes:
    headers=["Code famille","Famille / foyer","Responsable principal","Téléphone","Adresse","Enfants inscrits"]
    fs=[filters] if isinstance(filters,str) and filters else list(filters or [])
    return export_schooling_pdf_bytes(school=_school_meta(school_name,school),title="RÉPERTOIRE DES FAMILLES",filters=fs,headers=headers,rows=_family_rows(rows))


def family_directory_xlsx(*, school_name:str|None=None, school:dict[str,Any]|None=None, rows:list[dict[str,Any]], filters:str|list[str]="") -> bytes:
    headers=["Code famille","Famille / foyer","Responsable principal","Téléphone","Adresse","Enfants inscrits"]
    fs=[filters] if isinstance(filters,str) and filters else list(filters or [])
    return export_schooling_xlsx_bytes(school=_school_meta(school_name,school),title="RÉPERTOIRE DES FAMILLES",filters=fs,headers=headers,rows=_family_rows(rows))


def student_profile_pdf(*, school_name:str|None=None, school:dict[str,Any]|None=None, student:dict[str,Any]) -> bytes:
    name=' '.join(str(student.get(k) or '') for k in ('last_name','middle_name','first_name')).strip()
    enrollment=(student.get('enrollments') or [{}])[0]
    primary=next((g for g in (student.get('guardians') or []) if g.get('is_primary')),None) or ((student.get('guardians') or [None])[0])
    headers=['Champ','Valeur']
    rows=[
        ['Matricule',student.get('matricule')],['Élève',name],['Sexe',student.get('gender') or '—'],
        ['Année scolaire',enrollment.get('academic_year_label') or enrollment.get('academic_year_code') or '—'],['Section',enrollment.get('section_label') or '—'],['Classe',enrollment.get('class_label') or '—'],
        ['Date de naissance',student.get('birth_date') or 'À compléter'],['Lieu de naissance',student.get('birth_place') or 'À compléter'],['Nationalité',student.get('nationality') or 'À compléter'],
        ['Foyer',student.get('family_name') or '—'],['Responsable principal',(primary or {}).get('full_name') or 'À compléter'],['Téléphone',student.get('family_phone') or (primary or {}).get('phone') or 'À compléter'],['Adresse',student.get('address') or 'À compléter'],['Statut',_student_status_label(student.get('status'))],
    ]
    return export_schooling_pdf_bytes(school=_school_meta(school_name,school),title="FICHE ÉLÈVE",filters=[],headers=headers,rows=rows)
