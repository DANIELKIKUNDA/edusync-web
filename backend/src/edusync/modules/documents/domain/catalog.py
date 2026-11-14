from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass(frozen=True, slots=True)
class DocumentDefinition:
    code:str; label:str; module:str; formats:tuple[str,...]; preservation:str; status:str; source:str; capability:str|None=None
    # Codes under which the generated files are archived (exact code or « code. » prefix): the Documents page files
    # each archived document in the folder of its catalog family (owner report 2026-11-08: no « Autres documents »).
    archive_codes:tuple[str,...]=()
    def json(self): return {**asdict(self),"formats":list(self.formats),"archive_codes":list(self.archive_codes)}

# Canonical families established by the Desktop preservation audit. Exact Desktop function
# names remain deliberately unclaimed where the original archive bytes are unavailable.
CATALOG=(
 DocumentDefinition("finance.registers","Registres financiers","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.registers",)),
 DocumentDefinition("finance.summaries","Synthèses financières","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.summaries",)),
 DocumentDefinition("finance.receipts","Reçus","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.receipts","finance.receipt")),
 DocumentDefinition("finance.family_receipt_bundle","Lot familial de reçus","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory","documents.receipts.bundle.print",archive_codes=("finance.family_receipt_bundle","finance.receipts.bundle")),
 DocumentDefinition("finance.advance_funds","Fonds anticipés","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.advance_funds","finance.funds")),
 DocumentDefinition("finance.student_statement","Relevé élève","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.student_statement","students.account")),
 DocumentDefinition("finance.daily_report","Rapport journalier","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.daily_report","finance.reports.daily")),
 DocumentDefinition("finance.periodic_report","Rapport périodique","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("finance.periodic_report","finance.reports.periodic")),
 DocumentDefinition("effectifs.headcounts","Effectifs","Effectifs & dépôts",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4D", "headcounts.read",archive_codes=("effectifs.headcounts","headcounts")),
 DocumentDefinition("effectifs.official_register","Registre officiel","Effectifs & dépôts",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("effectifs.official_register",)),
 DocumentDefinition("effectifs.contributions","Contributions / dépôts","Effectifs & dépôts",("XLSX",),"MAXIMUM","WEB_IMPLEMENTED_PARTIAL","Point 4D","contributions.register.read",archive_codes=("effectifs.contributions","contributions.register","contributions")),
 DocumentDefinition("cash.journal","Journal de caisse","Caisse",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory",archive_codes=("cash.journal","finance.cash")),
 DocumentDefinition("schooling.student_import_template","Modèle d’import élèves","Imports",("XLSX",),"MAXIMUM","WEB_IMPLEMENTED","Point 5","documents.student_import_template.export",archive_codes=("schooling.student_import_template","students.import_template")),
 DocumentDefinition("schooling.student_directory","Liste des élèves","Élèves & inscriptions",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4C","students.directory.read",archive_codes=("schooling.student_directory","students.directory")),
 DocumentDefinition("schooling.family_directory","Répertoire des familles","Élèves & inscriptions",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4C","families.read",archive_codes=("schooling.family_directory","families.directory")),
 DocumentDefinition("schooling.student_profile","Fiches élèves","Élèves & inscriptions",("PDF",),"MAXIMUM","WEB_IMPLEMENTED","Fiche élève (2026-11-08)",archive_codes=("students.profile",)),
 DocumentDefinition("schooling.enrollment_register","Registre des inscriptions","Élèves & inscriptions",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED","Registre (2026-11-08)",archive_codes=("enrollments.register",)),
 DocumentDefinition("finance.recovery","Recouvrement","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Recouvrement (2026-11-08)",archive_codes=("finance.recovery",)),
 DocumentDefinition("personnel.staff_profile","Fiches agents","Personnel",("PDF",),"MAXIMUM","WEB_IMPLEMENTED","Fiche agent (2026-11-08)",archive_codes=("personnel.profile",)),
 DocumentDefinition("personnel.staff_register","Registre du personnel","Personnel",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED","Point 4B","personnel.directory.read",archive_codes=("personnel.staff_register","personnel.register")),
)

def catalog_family(document_code:str)->DocumentDefinition|None:
    """The catalog family of an archived document: the longest matching archive code (exact, or followed by « . »)."""
    best=None;size=-1
    for d in CATALOG:
        for c in d.archive_codes or (d.code,):
            if (document_code==c or document_code.startswith(c+".")) and len(c)>size: best,size=d,len(c)
    return best

def visible_catalog(permissions:frozenset[str])->list[dict]:
    return [d.json() for d in CATALOG if not d.capability or d.capability in permissions]
