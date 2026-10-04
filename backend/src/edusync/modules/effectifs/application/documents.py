from __future__ import annotations

from edusync.shared.infrastructure.xlsx_safety import XLSXWRITER_OPTIONS
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from edusync.modules.effectifs.domain.models import HeadcountRow, total_headcount

BLUE="#175CD3"
DARK="#123A8C"
LIGHT="#F8FAFC"
BORDER="#D0D5DD"


def _logo_path(school:dict[str,Any])->Path|None:
    for k in ("logo_path","logo_url"):
        v=school.get(k)
        if not v or str(v).startswith(("http://","https://")):continue
        p=Path(str(v))
        if p.exists() and p.is_file():return p
    return None


def _identity_lines(school:dict[str,Any])->list[str]:
    parts=[]
    address=" · ".join(str(x) for x in (school.get("address"),school.get("city"),school.get("province")) if x)
    contact=" · ".join(str(x) for x in (school.get("phone"),school.get("email")) if x)
    if address:parts.append(address)
    if contact:parts.append(contact)
    return parts


def _header_block(school:dict[str,Any], title:str, context:str, width:float):
    styles=getSampleStyleSheet()
    school_style=ParagraphStyle("school",parent=styles["Heading2"],fontName="Helvetica-Bold",fontSize=13,leading=15,textColor=colors.HexColor(DARK),alignment=TA_CENTER,spaceAfter=2)
    meta_style=ParagraphStyle("meta",parent=styles["Normal"],fontName="Helvetica",fontSize=7.5,leading=9,textColor=colors.HexColor("#475467"),alignment=TA_CENTER)
    title_style=ParagraphStyle("title",parent=styles["Heading1"],fontName="Helvetica-Bold",fontSize=12,leading=14,textColor=colors.HexColor(DARK),alignment=TA_CENTER,spaceBefore=3,spaceAfter=2)
    context_style=ParagraphStyle("context",parent=meta_style,fontSize=7)
    identity=[Paragraph(str(school.get("name") or "EduSync École"),school_style)]
    for line in _identity_lines(school):identity.append(Paragraph(line,meta_style))
    logo=_logo_path(school)
    if logo:
        try:left=Image(str(logo),width=15*mm,height=15*mm)
        except Exception:left=""
    else:left=""
    brand=Table([[left,identity,"" ]],colWidths=[19*mm,width-38*mm,19*mm])
    brand.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LINEBELOW",(0,0),(-1,-1),.45,colors.HexColor(BORDER)),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    return [brand,Spacer(1,2.2*mm),Paragraph(title,title_style),Paragraph(context,context_style),Spacer(1,3.5*mm)]


def _grouped_rows(rows:Iterable[HeadcountRow])->list[list[Any]]:
    data=[]
    for r in rows:
        data.append([r.section,r.label,r.enrolled.female,r.enrolled.male,r.enrolled.total,r.abandoned.female,r.abandoned.male,r.abandoned.total,r.transferred.female,r.transferred.male,r.transferred.total,r.active.female,r.active.male,r.active.total])
    return data


def headcounts_pdf(*,school:dict[str,Any],rows:list[HeadcountRow],title:str,scope_label:str,year_label:str)->bytes:
    buf=BytesIO();page=landscape(A4);margin=9*mm;avail=page[0]-2*margin
    doc=SimpleDocTemplate(buf,pagesize=page,leftMargin=margin,rightMargin=margin,topMargin=8*mm,bottomMargin=8*mm,title=title)
    styles=getSampleStyleSheet();h=ParagraphStyle("h",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=6.6,leading=7.5,textColor=colors.white,alignment=TA_CENTER)
    c=ParagraphStyle("c",parent=styles["Normal"],fontName="Helvetica",fontSize=6.4,leading=7.5,alignment=TA_CENTER)
    total=total_headcount(rows)
    ctx=f"Année scolaire : {year_label}  |  Périmètre : {scope_label}  |  Édité le {datetime.now():%d/%m/%Y %H:%M}"
    story=_header_block(school,title,ctx,avail)
    top=["Section","Classe / regroupement","Inscrits","","","Abandons","","","Transférés","","","Élèves actifs","",""]
    sub=["","","F","G","T","F","G","T","F","G","T","F","G","T"]
    body=_grouped_rows(rows)+[["","Total général",total.enrolled.female,total.enrolled.male,total.enrolled.total,total.abandoned.female,total.abandoned.male,total.abandoned.total,total.transferred.female,total.transferred.male,total.transferred.total,total.active.female,total.active.male,total.active.total]]
    data=[[Paragraph(str(x),h) if x else "" for x in top],[Paragraph(str(x),h) if x else "" for x in sub]]+[[Paragraph(str(x),c) for x in row] for row in body]
    widths=[24*mm,40*mm]+[13.1*mm]*12
    table=Table(data,colWidths=widths,repeatRows=2,hAlign="CENTER")
    cmds=[
      ("BACKGROUND",(0,0),(-1,1),colors.HexColor(BLUE)),("TEXTCOLOR",(0,0),(-1,1),colors.white),
      ("SPAN",(0,0),(0,1)),("SPAN",(1,0),(1,1)),
      ("SPAN",(2,0),(4,0)),("SPAN",(5,0),(7,0)),("SPAN",(8,0),(10,0)),("SPAN",(11,0),(13,0)),
      ("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
      ("GRID",(0,0),(-1,-1),.3,colors.HexColor(BORDER)),("ROWBACKGROUNDS",(0,2),(-1,-2),[colors.white,colors.HexColor(LIGHT)]),
      ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#E8F0FE")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
      ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]
    table.setStyle(TableStyle(cmds));story.append(table);doc.build(story);return buf.getvalue()


def headcounts_xlsx(*,school:dict[str,Any],rows:list[HeadcountRow],title:str,scope_label:str,year_label:str,sheet_name:str="Par classe")->bytes:
    # Server-side equivalent of the certified Desktop workbook. xlsxwriter preserves merged two-level headings.
    import xlsxwriter
    out=BytesIO();wb=xlsxwriter.Workbook(out,XLSXWRITER_OPTIONS);ws=wb.add_worksheet(sheet_name[:31])
    wb.set_properties({"title":title,"company":str(school.get("name") or "EduSync")})
    f_school=wb.add_format({"bold":True,"font_size":15,"font_color":DARK,"align":"center","valign":"vcenter"})
    f_meta=wb.add_format({"font_size":9,"font_color":"#475467","align":"center","valign":"vcenter"})
    f_title=wb.add_format({"bold":True,"font_size":12,"font_color":DARK,"align":"center","valign":"vcenter"})
    f_group=wb.add_format({"bold":True,"font_color":"white","bg_color":BLUE,"border":1,"border_color":BORDER,"align":"center","valign":"vcenter"})
    f_cell=wb.add_format({"border":1,"border_color":BORDER,"align":"center","valign":"vcenter"})
    f_alt=wb.add_format({"border":1,"border_color":BORDER,"align":"center","valign":"vcenter","bg_color":LIGHT})
    f_total=wb.add_format({"bold":True,"border":1,"border_color":BORDER,"align":"center","valign":"vcenter","bg_color":"#E8F0FE"})
    ws.merge_range(0,0,0,13,str(school.get("name") or "EduSync École"),f_school)
    meta=" | ".join(_identity_lines(school))
    ws.merge_range(1,0,1,13,meta or "Document officiel EduSync",f_meta)
    ws.merge_range(2,0,2,13,title,f_title)
    ws.merge_range(3,0,3,13,f"Année scolaire : {year_label} | Périmètre : {scope_label} | Édité le {datetime.now():%d/%m/%Y %H:%M}",f_meta)
    ws.merge_range(4,0,5,0,"Section",f_group);ws.merge_range(4,1,5,1,"Classe / regroupement",f_group)
    for col,label in ((2,"Inscrits"),(5,"Abandons"),(8,"Transférés"),(11,"Élèves actifs")):
        ws.merge_range(4,col,4,col+2,label,f_group)
        for j,s in enumerate(("F","G","T")):ws.write(5,col+j,s,f_group)
    ws.set_column(0,0,18);ws.set_column(1,1,26);ws.set_column(2,13,8)
    total=total_headcount(rows)
    for i,row in enumerate(_grouped_rows(rows),start=6):
        fmt=f_alt if i%2 else f_cell
        for j,v in enumerate(row):ws.write(i,j,v,fmt)
    tr=["","Total général",total.enrolled.female,total.enrolled.male,total.enrolled.total,total.abandoned.female,total.abandoned.male,total.abandoned.total,total.transferred.female,total.transferred.male,total.transferred.total,total.active.female,total.active.male,total.active.total]
    ti=6+len(rows)
    for j,v in enumerate(tr):ws.write(ti,j,v,f_total)
    ws.freeze_panes(6,2);ws.autofilter(5,0,ti,13);ws.hide_gridlines(2);ws.set_landscape();ws.fit_to_pages(1,0);ws.set_paper(9)
    logo=_logo_path(school)
    if logo:
        try:ws.insert_image(0,0,str(logo),{"x_scale":.30,"y_scale":.30,"x_offset":4,"y_offset":2})
        except Exception:pass
    wb.close();out.seek(0);return out.getvalue()


def deposits_xlsx(*,school:dict[str,Any],rows:list[dict[str,Any]],scope_label:str,year_label:str)->bytes:
    import xlsxwriter
    out=BytesIO();wb=xlsxwriter.Workbook(out,XLSXWRITER_OPTIONS);ws=wb.add_worksheet("Dépôts matériels")
    f_title=wb.add_format({"bold":True,"font_size":14,"font_color":DARK,"align":"center"});f_meta=wb.add_format({"font_size":9,"font_color":"#475467","align":"center"});f_h=wb.add_format({"bold":True,"font_color":"white","bg_color":BLUE,"border":1,"align":"center"});f=wb.add_format({"border":1,"border_color":BORDER});f_num=wb.add_format({"border":1,"border_color":BORDER,"num_format":"0.###"})
    headers=["Date","Matricule","Élève","Section","Classe","Contribution","Quantité","Unité","Enregistré par","Observation"]
    ws.merge_range(0,0,0,len(headers)-1,str(school.get("name") or "EduSync École"),f_title);ws.merge_range(1,0,1,len(headers)-1," | ".join(_identity_lines(school)),f_meta);ws.merge_range(2,0,2,len(headers)-1,"REGISTRE DES DÉPÔTS MATÉRIELS",f_title);ws.merge_range(3,0,3,len(headers)-1,f"Année scolaire : {year_label} | Périmètre : {scope_label} | Total lignes : {len(rows)}",f_meta)
    for j,h in enumerate(headers):ws.write(4,j,h,f_h)
    for i,r in enumerate(rows,start=5):
        values=[r.get("deposited_on"),r.get("matricule"),r.get("student_name"),r.get("section_label"),r.get("class_label"),r.get("contribution_label"),float(r.get("quantity") or 0),r.get("unit"),r.get("recorded_by_name") or "—",r.get("notes") or ""]
        for j,v in enumerate(values):ws.write(i,j,v,f_num if j==6 else f)
    ws.set_column(0,0,12);ws.set_column(1,1,16);ws.set_column(2,2,28);ws.set_column(3,5,19);ws.set_column(6,7,11);ws.set_column(8,9,22);ws.freeze_panes(5,0);ws.autofilter(4,0,max(4,4+len(rows)),len(headers)-1);ws.hide_gridlines(2)
    wb.close();out.seek(0);return out.getvalue()
