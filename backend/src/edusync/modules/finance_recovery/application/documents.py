from __future__ import annotations
from decimal import Decimal
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font,Alignment,PatternFill,Border,Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle

def _m(v): return f"{Decimal(str(v or 0)):,.0f}".replace(',',' ')
def monthly_xlsx(*,school,year_label,currency,rows,total):
    wb=Workbook();ws=wb.active;ws.title='Suivi mensuel';ws.merge_cells('A1:J1');ws['A1']=school.get('name','École');ws['A1'].font=Font(size=16,bold=True);ws['A1'].alignment=Alignment(horizontal='center')
    ws.merge_cells('A2:J2');ws['A2']='SUIVI MENSUEL DU RECOUVREMENT';ws['A2'].font=Font(size=13,bold=True);ws['A2'].alignment=Alignment(horizontal='center')
    ws.merge_cells('A3:J3');ws['A3']=f"Année scolaire : {year_label} · Devise : {currency}";ws['A3'].alignment=Alignment(horizontal='center')
    headers=['Mois','Redevables','En ordre','Non en ordre','Attendu','Encaissé caisse','Régularisé hors caisse','Régularisé total','Reste','Taux']
    for j,h in enumerate(headers,1):c=ws.cell(5,j,h);c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='1F4E78');c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
    allrows=[*rows,total]
    for i,r in enumerate(allrows,6):
        vals=[r.get('month_label'),r.get('debtors'),r.get('in_order'),r.get('not_in_order'),r.get('expected'),r.get('cash_collected'),r.get('outside_cash'),r.get('regularized_total'),r.get('remaining'),float(r.get('recovery_rate') or 0)/100]
        for j,v in enumerate(vals,1):ws.cell(i,j,v)
        if r.get('month')=='TOTAL':
            for c in ws[i]:c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='D9EAF7')
        for j in range(5,10):ws.cell(i,j).number_format='#,##0.00'
        ws.cell(i,10).number_format='0.0%'
    widths=[16,13,12,14,17,18,22,20,17,12]
    for j,w in enumerate(widths,1):ws.column_dimensions[get_column_letter(j)].width=w
    ws.freeze_panes='A6';ws.auto_filter.ref=f'A5:J{5+len(allrows)}';ws.sheet_view.showGridLines=False;ws.print_title_rows='1:5';ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1;ws.sheet_properties.pageSetUpPr.fitToPage=True
    neutralize_formulas(wb);out=BytesIO();wb.save(out);return out.getvalue()
def monthly_pdf(*,school,year_label,currency,rows,total):
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=landscape(A4),rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24);styles=getSampleStyleSheet();story=[Paragraph(school.get('name','École'),styles['Title']),Paragraph('SUIVI MENSUEL DU RECOUVREMENT',ParagraphStyle('sub',parent=styles['Heading2'],alignment=1)),Paragraph(f'Année scolaire : {year_label} · Devise : {currency}',ParagraphStyle('meta',parent=styles['Normal'],alignment=1)),Spacer(1,12)]
    data=[['Mois','Redev.','En ordre','Non ordre','Attendu','Caisse','Hors caisse','Régul. total','Reste','Taux']]
    for r in [*rows,total]:data.append([r.get('month_label'),'' if r.get('debtors') is None else r.get('debtors'),'' if r.get('in_order') is None else r.get('in_order'),'' if r.get('not_in_order') is None else r.get('not_in_order'),_m(r.get('expected')),_m(r.get('cash_collected')),_m(r.get('outside_cash')),_m(r.get('regularized_total')),_m(r.get('remaining')),f"{r.get('recovery_rate',0)} %"])
    t=Table(data,repeatRows=1,colWidths=[60,48,48,52,70,70,78,78,70,45]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1F4E78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#D9EAF7')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#CBD5E1')),('ALIGN',(1,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTSIZE',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-2),[colors.white,colors.HexColor('#F8FAFC')])]))
    story+=[t,Spacer(1,8),Paragraph('Les effectifs mensuels ne sont pas additionnés dans le total général. Les montants et le taux global sont recalculés sur les obligations nettes de l’année sélectionnée.',styles['Normal'])];doc.build(story);return out.getvalue()

MONTHS_FR={'janvier':1,'février':2,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'août':8,'aout':8,'septembre':9,'octobre':10,'novembre':11,'décembre':12,'decembre':12}
def _terminal_for(st,col):
    t=st.get('terminal');
    if not t:return None
    if col.get('group')!='MONTHLY':return None
    m=MONTHS_FR.get(str(col.get('label','')).lower().strip());d=t.get('effective_date')
    if not m or not d:return None
    return ('Abandon' if t['type']=='ABANDON' else 'Transféré') if (d.month<=m if d.year==getattr(d,'year',0) else False) else None

def class_register_xlsx(*,school,year_label,data):
    wb=Workbook();ws=wb.active;ws.title='Registre de classe';cols=data['columns'];n=3+len(cols)
    for row,text,size in [(1,school.get('name','École'),16),(2,f"REGISTRE FINANCIER DE CLASSE — {data['class_label']} — {year_label}",13),(3,f"Devise : {data['currency']}",10)]:
        ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=n);ws.cell(row,1,text).font=Font(size=size,bold=row<3);ws.cell(row,1).alignment=Alignment(horizontal='center')
    ws.merge_cells('A5:A6');ws['A5']='N°';ws.merge_cells('B5:B6');ws['B5']='Élève';ws.merge_cells('C5:C6');ws['C5']="Date d'inscription"
    c=4;i=0
    while i<len(cols):
        parent=cols[i]['parent'] or cols[i]['label'];j=i+1
        while j<len(cols) and cols[j]['parent']==cols[i]['parent'] and cols[j]['group']==cols[i]['group'] and cols[i]['parent']:j+=1
        if j-i>1: ws.merge_cells(start_row=5,start_column=c,end_row=5,end_column=c+j-i-1)
        ws.cell(5,c,parent)
        for k in range(i,j):ws.cell(6,c+k-i,cols[k]['label'])
        c+=j-i;i=j
    thin=Side(style='thin')
    for row in ws.iter_rows(min_row=5,max_row=6,min_col=1,max_col=n):
        for cell in row:cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True);cell.fill=PatternFill('solid',fgColor='E9EEF5');cell.border=Border(left=thin,right=thin,top=thin,bottom=thin)
    for idx,st in enumerate(data['students'],1):
        r=6+idx;ws.cell(r,1,idx);ws.cell(r,2,st['student_name']);ws.cell(r,3,st['enrolled_on'])
        for j,col in enumerate(cols,4):
            cell=st['cells'].get(col['key']);term=_terminal_for(st,col)
            if term: val=term
            elif cell: val=float(Decimal(str(cell['paid'] or 0))+Decimal(str(cell['advance'] or 0))) or ''
            else: val=''
            ws.cell(r,j,val);ws.cell(r,j).alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
    r=7+len(data['students']);f=data['footer'];footer=[('Élèves redevables',f['debtors']),('Montant attendu',float(f['expected'])),('Montant régularisé',float(f['regularized'])),('Reste à recouvrer',float(f['remaining'])),('Élèves à l’ordre',f['in_order']),('Élèves non à l’ordre',f['not_in_order']),('Taux de recouvrement',float(f['recovery_rate'])/100)]
    for label,val in footer:
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=max(3,n-1));ws.cell(r,1,label).font=Font(bold=True);ws.cell(r,n,val).font=Font(bold=True);ws.cell(r,n).number_format='0.0%' if label.startswith('Taux') else '#,##0';r+=1
    ws.freeze_panes='D7';ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1
    ws.column_dimensions['A'].width=6;ws.column_dimensions['B'].width=30;ws.column_dimensions['C'].width=16
    for j in range(4,n+1):ws.column_dimensions[get_column_letter(j)].width=14
    neutralize_formulas(wb);out=BytesIO();wb.save(out);return out.getvalue()

def class_register_pdf(*,school,year_label,data):
    from reportlab.lib.pagesizes import A3,landscape
    styles=getSampleStyleSheet();small=ParagraphStyle('small2',parent=styles['Normal'],fontSize=6.3,leading=7.3,alignment=1)
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=landscape(A3),leftMargin=18,rightMargin=18,topMargin=18,bottomMargin=18)
    story=[Paragraph(f"<b>{school.get('name','École')}</b>",styles['Title']),Paragraph(f"<b>REGISTRE FINANCIER DE CLASSE — {data['class_label']}</b>",styles['Heading2']),Paragraph(f"Année scolaire : {year_label} · Devise : {data['currency']}",small),Spacer(1,8)]
    cols=data['columns'];rows=[['N°','Élève',"Date d'inscription"]+[c['label'] for c in cols]]
    for i,st in enumerate(data['students'],1):
        vals=[]
        for col in cols:
            cell=st['cells'].get(col['key']);term=_terminal_for(st,col)
            vals.append(term or (_m(Decimal(str(cell['paid'] or 0))+Decimal(str(cell['advance'] or 0))) if cell and (cell['paid'] or cell['advance']) else ''))
        rows.append([i,st['student_name'],str(st['enrolled_on'])]+vals)
    t=Table(rows,repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EEF5')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#94A3B8')),('FONTSIZE',(0,0),(-1,-1),6),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    f=data['footer'];foot=[['Élèves redevables',f['debtors']],['Montant attendu',_m(f['expected'])],['Montant régularisé',_m(f['regularized'])],['Reste à recouvrer',_m(f['remaining'])],['Élèves à l’ordre',f['in_order']],['Élèves non à l’ordre',f['not_in_order']],['Taux de recouvrement',f"{f['recovery_rate']} %"]]
    ft=Table(foot,colWidths=[150,100]);ft.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.HexColor('#94A3B8')),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('ALIGN',(1,0),(1,-1),'RIGHT'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#D9EAF7'))]))
    story += [t,Spacer(1,10),ft];doc.build(story);return out.getvalue()

def summary_xlsx(*,school,title,year_label,currency,rows,total,first='Libellé'):
    wb=Workbook();ws=wb.active;ws.title='Synthèse';headers=[first,'Redevables','En ordre','Non en ordre','Attendu','Encaissé caisse','Régul. hors caisse','Régul. total','Reste','Taux']
    ws.merge_cells('A1:J1');ws['A1']=school.get('name','École');ws['A1'].font=Font(size=16,bold=True);ws['A1'].alignment=Alignment(horizontal='center')
    ws.merge_cells('A2:J2');ws['A2']=title;ws['A2'].font=Font(size=13,bold=True);ws['A2'].alignment=Alignment(horizontal='center');ws.merge_cells('A3:J3');ws['A3']=f'Année scolaire : {year_label} · Devise : {currency}';ws['A3'].alignment=Alignment(horizontal='center')
    for j,h in enumerate(headers,1):ws.cell(5,j,h).font=Font(bold=True)
    for i,r in enumerate([*rows,total],6):
        vals=[r.get('label') or r.get('month_label'),r.get('debtors'),r.get('in_order'),r.get('not_in_order'),r.get('expected'),r.get('cash_collected'),r.get('outside_cash'),r.get('regularized_total'),r.get('remaining'),float(r.get('recovery_rate') or 0)/100]
        for j,v in enumerate(vals,1):ws.cell(i,j,v)
        ws.cell(i,10).number_format='0.0%'
        if i==5+len(rows)+1:
            for c in ws[i]:c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='D9EAF7')
    ws.freeze_panes='A6';ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1
    neutralize_formulas(wb);out=BytesIO();wb.save(out);return out.getvalue()

def summary_pdf(*,school,title,year_label,currency,rows,total,first='Libellé'):
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=20,bottomMargin=20);styles=getSampleStyleSheet();story=[Paragraph(school.get('name','École'),styles['Title']),Paragraph(title,styles['Heading2']),Paragraph(f'Année scolaire : {year_label} · Devise : {currency}',styles['Normal']),Spacer(1,8)]
    data=[[first,'Redev.','En ordre','Non ordre','Attendu','Caisse','Hors caisse','Régul. total','Reste','Taux']]
    for r in [*rows,total]:data.append([r.get('label') or r.get('month_label'),r.get('debtors',''),r.get('in_order',''),r.get('not_in_order',''),_m(r.get('expected')),_m(r.get('cash_collected')),_m(r.get('outside_cash')),_m(r.get('regularized_total')),_m(r.get('remaining')),f"{r.get('recovery_rate',0)} %"])
    t=Table(data,repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1F4E78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#D9EAF7')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),6.5)]));story.append(t);doc.build(story);return out.getvalue()


# ---------------------------------------------------------------- 2026-10-25 — Suivi financier : liste à emporter en classe
def followup_pdf(*, school, year_label, data, only_not_in_order=True):
    """Printable list for the person who goes into the classroom: pupils not in order (or all), what they owe, which periods."""
    rows = [r for r in data["rows"] if r["status"] in ("PARTIAL", "NONE")] if only_not_in_order else [r for r in data["rows"] if r["status"] != "NA"]
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24); st = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=st["Normal"], fontSize=8, leading=10)
    title = "ÉLÈVES NON EN ORDRE" if only_not_in_order else "SITUATION DES ÉLÈVES"
    story = [Paragraph(school.get("name", "École"), st["Title"]), Paragraph(f"{title} — {data['class_label']}", st["Heading2"]),
             Paragraph(f"{data['title']} · Année {year_label} · Devise {data['currency']} · {data['counts']['in_order']} en ordre, {data['counts']['not_in_order']} non en ordre sur {data['counts']['students']}", st["Normal"]), Spacer(1, 8)]
    table = [["N°", "Matricule", "Élève", "Reste dû", "Périodes non réglées", "Situation", "Obs."]]
    for i, r in enumerate(rows, 1):
        table.append([str(i), r["matricule"] or "", Paragraph(r["student_name"] or "", small), _m(r["remaining"]), Paragraph(", ".join(r["missing"]) or "—", small), r["status_label"], ""])
    if len(table) == 1:
        table.append(["", "", "Tous les élèves sont en ordre.", "", "", "", ""])
    t = Table(table, repeatRows=1, colWidths=[24, 62, 150, 62, 150, 52, 44])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d1dc")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (3, 1), (3, -1), "RIGHT"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fc")])]))
    story += [t, Spacer(1, 10), Paragraph(f"Reste à recouvrer : {_m(data['remaining'])} {data['currency']} · Taux {data['rate']} %", st["Normal"])]
    doc.build(story); return out.getvalue()


def followup_xlsx(*, school, year_label, data):
    wb = Workbook(); ws = wb.active; ws.title = "Suivi financier"
    headers = ["N°", "Matricule", "Élève", "Situation", "Dû", "Réglé", "Reste dû", "Périodes non réglées"]
    for row, value, size in ((1, school.get("name", "École"), 15), (2, f"SUIVI FINANCIER — {data['class_label']}", 12), (3, f"{data['title']} · Année {year_label} · {data['currency']}", 10)):
        ws.merge_cells(f"A{row}:H{row}"); ws[f"A{row}"] = value; ws[f"A{row}"].font = Font(size=size, bold=row < 3); ws[f"A{row}"].alignment = Alignment(horizontal="center")
    for j, h in enumerate(headers, 1):
        c = ws.cell(5, j, h); c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F4E78"); c.alignment = Alignment(horizontal="center")
    rows = [r for r in data["rows"] if r["status"] != "NA"]
    for i, r in enumerate(rows, 6):
        vals = [i - 5, r["matricule"], r["student_name"], r["status_label"], float(Decimal(r["due"])), float(Decimal(r["settled"])), float(Decimal(r["remaining"])), ", ".join(r["missing"])]
        for j, v in enumerate(vals, 1):
            ws.cell(i, j, v)
        for j in (5, 6, 7):
            ws.cell(i, j).number_format = "#,##0.00"
        if r["status"] != "OK":
            ws.cell(i, 4).font = Font(bold=True, color="B42318")
    for j, w in enumerate([6, 14, 34, 14, 14, 14, 14, 44], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A6"; ws.auto_filter.ref = f"A5:H{max(5, 5 + len(rows))}"; ws.sheet_view.showGridLines = False
    neutralize_formulas(wb); out = BytesIO(); wb.save(out); return out.getvalue()
