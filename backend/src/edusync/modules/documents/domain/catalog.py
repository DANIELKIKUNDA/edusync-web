from __future__ import annotations
from dataclasses import asdict, dataclass

@dataclass(frozen=True, slots=True)
class DocumentDefinition:
    code:str; label:str; module:str; formats:tuple[str,...]; preservation:str; status:str; source:str; capability:str|None=None
    def json(self): return {**asdict(self),"formats":list(self.formats)}

# Canonical families established by the Desktop preservation audit. Exact Desktop function
# names remain deliberately unclaimed where the original archive bytes are unavailable.
CATALOG=(
 DocumentDefinition("finance.registers","Registres financiers","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.summaries","Synthèses financières","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.receipts","Reçus","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.family_receipt_bundle","Lot familial de reçus","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory","documents.receipts.bundle.print"),
 DocumentDefinition("finance.advance_funds","Fonds anticipés","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.student_statement","Relevé élève","Finance",("PDF",),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.daily_report","Rapport journalier","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("finance.periodic_report","Rapport périodique","Finance",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("effectifs.headcounts","Effectifs","Effectifs & dépôts",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4D", "headcounts.read"),
 DocumentDefinition("effectifs.official_register","Registre officiel","Effectifs & dépôts",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("effectifs.contributions","Contributions / dépôts","Effectifs & dépôts",("XLSX",),"MAXIMUM","WEB_IMPLEMENTED_PARTIAL","Point 4D","contributions.register.read"),
 DocumentDefinition("cash.journal","Journal de caisse","Caisse",("PDF","XLSX"),"MAXIMUM","DESKTOP_GOLDEN_REQUIRED","Desktop canonical inventory"),
 DocumentDefinition("schooling.student_import_template","Modèle d’import élèves","Imports",("XLSX",),"MAXIMUM","WEB_IMPLEMENTED","Point 5","documents.student_import_template.export"),
 DocumentDefinition("schooling.student_directory","Liste des élèves","Élèves & inscriptions",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4C","students.directory.read"),
 DocumentDefinition("schooling.family_directory","Répertoire des familles","Élèves & inscriptions",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED_GOLDEN_PRESERVED","Point 4C","families.read"),
 DocumentDefinition("personnel.staff_register","Registre du personnel","Personnel",("PDF","XLSX"),"MAXIMUM","WEB_IMPLEMENTED","Point 4B","personnel.directory.read"),
)

def visible_catalog(permissions:frozenset[str])->list[dict]:
    return [d.json() for d in CATALOG if not d.capability or d.capability in permissions]
