from __future__ import annotations
from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
import hashlib
from io import BytesIO
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation

CONTRACT_VERSION='1.0'
META_SHEET='_EDUSYNC_CONTRACT'
DATA_SHEET='Données'
INSTRUCTIONS_SHEET='Instructions'
REF_SHEET='Référentiels'

STUDENTS_V1_0=['Nom*','Postnom*','Prénom*','Sexe*','Classe*','Date naissance','Lieu naissance','Nationalité','Adresse','Nom responsable','Téléphone responsable','E-mail responsable','École de provenance','Observation']
CONTRACTS={
 # 1.1 (owner, 2026-11-01): « la date d'inscription doit rester la date réelle à laquelle l'élève a pris officiellement
 # les inscriptions » — optional last column; empty = day of the import (1.0 behaviour). 1.0 files stay accepted.
 'STUDENTS': {'id':'EDUSYNC-STUDENTS-v1','version':'1.1','headers':STUDENTS_V1_0+['Date inscription'],'legacy':{'1.0':STUDENTS_V1_0}},
 'STAFF': {'id':'EDUSYNC-STAFF-v1','headers':['Matricule*','Nom*','Postnom','Prénom','Sexe','Catégorie*','Date naissance','Téléphone','E-mail','Adresse','Qualification','Spécialité','Date engagement','Statut','Observation']},
 'FINANCE_HISTORY': {'id':'EDUSYNC-FINANCE-HISTORY-v1','headers':['Année scolaire*','Matricule élève*','Frais*','Période','Montant*','Devise*','Date paiement*','Référence historique','Observation']},
}

def fingerprint(headers:list[str])->str:
 return hashlib.sha256('\x1f'.join(headers).encode()).hexdigest()

def contract_version(kind:str)->str:
 return CONTRACTS[kind].get('version',CONTRACT_VERSION)

def build_template(kind:str, *, school_name:str='EduSync École', references:dict[str,list[str]]|None=None)->bytes:
 c=CONTRACTS[kind]; headers=c['headers']; refs=references or {}; version=contract_version(kind)
 wb=Workbook(); ws=wb.active; ws.title={'STUDENTS':'Import élèves','STAFF':'Import personnel','FINANCE_HISTORY':'Historique financier'}[kind]; data_sheet=ws.title; ws.sheet_view.showGridLines=False
 title={'STUDENTS':'IMPORT DES ÉLÈVES','STAFF':'IMPORT DU PERSONNEL','FINANCE_HISTORY':'REPRISE HISTORIQUE FINANCIÈRE'}[kind]
 ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers)); x=ws.cell(1,1,school_name); x.font=Font(size=16,bold=True,color='123A8C');x.alignment=Alignment(horizontal='center')
 ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers));x=ws.cell(2,1,f'EDUSYNC — {title} — MODÈLE OFFICIEL {version}');x.font=Font(size=11,bold=True,color='123A8C');x.alignment=Alignment(horizontal='center')
 msg='Remplissez uniquement les lignes de données. Ne renommez, ne déplacez et ne supprimez aucune colonne.'
 if kind=='FINANCE_HISTORY': msg+=' Ces lignes restent hors caisse et ne créent aucun reçu EduSync.'
 ws.merge_cells(start_row=3,start_column=1,end_row=3,end_column=len(headers));ws.cell(3,1,msg).alignment=Alignment(horizontal='center',wrap_text=True)
 fill=PatternFill('solid',fgColor='175CD3');thin=Side(style='thin',color='D0D5DD')
 for j,h in enumerate(headers,1):
  cell=ws.cell(5,j,h);cell.font=Font(bold=True,color='FFFFFF');cell.fill=fill;cell.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True);cell.border=Border(left=thin,right=thin,top=thin,bottom=thin);cell.protection=Protection(locked=True)
 ws.freeze_panes='A6';ws.auto_filter.ref=f'A5:{ws.cell(5,len(headers)).column_letter}2005'
 for i,h in enumerate(headers,1): ws.column_dimensions[ws.cell(5,i).column_letter].width=max(14,min(28,len(h)+6))
 # Protect structure/header while data cells remain editable. No password: prevents accidents, not a security boundary.
 for row in ws.iter_rows(min_row=6,max_row=2005,max_col=len(headers)):
  for cell in row: cell.protection=Protection(locked=False)
 ws.protection.sheet=True;ws.protection.formatColumns=True;ws.protection.formatRows=True;ws.protection.insertColumns=True;ws.protection.deleteColumns=True
 ins=wb.create_sheet(INSTRUCTIONS_SHEET);ins.column_dimensions['A'].width=115
 rules=['RÈGLES D’IMPORT EDUSYNC',f'Contrat : {c["id"]} — version {version}','1. Utilisez uniquement ce modèle téléchargé depuis EduSync.','2. Une ligne = un enregistrement. Les colonnes avec * sont obligatoires.','3. Ne renommez, ne déplacez, n’ajoutez ni ne supprimez les colonnes.','4. EduSync vérifie le contrat, sa version et l’empreinte des colonnes avant de lire les données.','5. Le fichier passe toujours par analyse, staging et prévisualisation avant écriture définitive.','6. Une erreur bloque le lot ; un avertissement exige une confirmation explicite.','7. Conservez le fichier source comme pièce de traçabilité.']
 if kind=='STUDENTS': rules += ['8. Sexe : F ou M. La classe doit exister dans l’année choisie.','9. Les foyers ne sont jamais fusionnés silencieusement.','10. Date inscription : la date réelle de l’inscription (JJ/MM/AAAA). Vide = date du jour de l’import.']
 elif kind=='STAFF': rules += ['8. Catégorie : ENSEIGNANT, ADMINISTRATIF, OUVRIER ou AUTRE.','9. Un matricule déjà existant bloque la ligne.']
 else: rules += ['8. La reprise financière est HORS CAISSE : aucun nouveau paiement, mouvement de caisse ou reçu EduSync.','9. Une référence historique est fortement recommandée et sert au contrôle anti-doublon.']
 for i,t in enumerate(rules,1):ins.cell(i,1,t);ins.cell(i,1).alignment=Alignment(wrap_text=True,vertical='top');ins.cell(i,1).font=Font(bold=i<=2,size=14 if i==1 else 11,color='123A8C' if i<=2 else '000000')
 ref=wb.create_sheet(REF_SHEET); ref.sheet_state='hidden'; col=1
 default_refs={}
 if kind=='STUDENTS':default_refs={'Sexe*':['F','M']}
 if kind=='STAFF':default_refs={'Sexe':['F','M'],'Catégorie*':['ENSEIGNANT','ADMINISTRATIF','OUVRIER','AUTRE'],'Statut':['ACTIF','INACTIF','SUSPENDU']}
 if kind=='FINANCE_HISTORY':default_refs={'Devise*':['CDF','USD']}
 default_refs.update(refs)
 for label,values in default_refs.items():
  ref.cell(1,col,label)
  for r,v in enumerate(values,2):ref.cell(r,col,v)
  if values and label in headers:
   idx=headers.index(label)+1; letter=ref.cell(1,col).column_letter
   dv=DataValidation(type='list',formula1=f"'{REF_SHEET}'!${letter}$2:${letter}${len(values)+1}",allow_blank=not label.endswith('*'));ws.add_data_validation(dv);dv.add(f'{ws.cell(6,idx).column_letter}6:{ws.cell(2005,idx).column_letter}2005')
  col+=1
 meta=wb.create_sheet(META_SHEET);meta.sheet_state='veryHidden'
 pairs=[('product','EduSync'),('contract_id',c['id']),('contract_version',version),('kind',kind),('header_fingerprint',fingerprint(headers)),('data_sheet',data_sheet),('header_row','5')]
 for r,(k,v) in enumerate(pairs,1):meta.cell(r,1,k);meta.cell(r,2,v)
 wb.security.lockStructure=True
 neutralize_formulas(wb);out=BytesIO();wb.save(out);return out.getvalue()

def read_official_xlsx(data:bytes, kind:str)->list[tuple[int,dict]]:
 try: wb=load_workbook(BytesIO(data),read_only=True,data_only=True)
 except Exception as e: raise ValueError('Fichier XLSX illisible') from e
 c=CONTRACTS[kind]
 if META_SHEET not in wb.sheetnames:raise ValueError("Ce fichier n’est pas un modèle officiel EduSync. Téléchargez d’abord le modèle proposé dans l’écran d’import.")
 meta=wb[META_SHEET]; values={str(meta.cell(r,1).value):str(meta.cell(r,2).value or '') for r in range(1,20) if meta.cell(r,1).value}
 if values.get('product')!='EduSync' or values.get('contract_id')!=c['id']:raise ValueError("Modèle EduSync incompatible avec ce type d’import")
 accepted={contract_version(kind):c['headers'],**c.get('legacy',{})}
 expected=accepted.get(values.get('contract_version'))
 if expected is None:raise ValueError(f"Version de modèle non prise en charge : {values.get('contract_version') or 'inconnue'}. Téléchargez le modèle actuel.")
 if values.get('header_fingerprint')!=fingerprint(expected):raise ValueError('Empreinte du contrat d’import invalide')
 sheet=values.get('data_sheet',DATA_SHEET);row=int(values.get('header_row','5'))
 if sheet not in wb.sheetnames:raise ValueError("Feuille de données EduSync absente")
 ws=wb[sheet];headers=[str(x.value or '').strip() for x in ws[row]][:len(expected)]
 if headers!=expected:raise ValueError('Structure du modèle EduSync modifiée : restaurez les colonnes officielles')
 out=[]
 for rn,vals in enumerate(ws.iter_rows(min_row=row+1,max_col=len(expected),values_only=True),row+1):
  if any(v not in (None,'') for v in vals):out.append((rn,dict(zip(expected,vals))))
 return out
