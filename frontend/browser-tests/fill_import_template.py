"""Fills an official EduSync import template downloaded from the app (local import walkthrough, 2026-10-25).
Usage: python fill_import_template.py <kind STUDENTS|STAFF|FINANCE_HISTORY> <template.xlsx> <out.xlsx> <run> [bad]
Valid values (classes, categories, fees, years) are read from the template's own « Référentiels » sheet; « bad » adds a
row that must be refused (missing required value) so the walkthrough proves an error blocks the batch."""
from __future__ import annotations

import sys
from datetime import date

from openpyxl import load_workbook

kind, src, out, run = sys.argv[1:5]
bad = len(sys.argv) > 5 and sys.argv[5] == "bad"
wb = load_workbook(src)
data_name = {"STUDENTS": "Import élèves", "STAFF": "Import personnel", "FINANCE_HISTORY": "Historique financier"}[kind]
ws = wb[data_name]
headers = [c.value for c in ws[5] if c.value]
refs: dict[str, list[str]] = {}
if "Référentiels" in wb.sheetnames:
    r = wb["Référentiels"]
    for col in r.iter_cols(min_row=1, values_only=True):
        if col and col[0]:
            refs[str(col[0])] = [str(v) for v in col[1:] if v not in (None, "")]
def ref(name: str, default: str) -> str:
    for k, v in refs.items():
        if name.lower() in k.lower() and v:
            return v[0]
    return default

rows: list[dict[str, object]] = []
if kind == "STUDENTS":
    klass = ref("Classe", "")
    for i, (sex, first) in enumerate([("M", "Patrick"), ("F", "Ruth"), ("F", "Esther")], 1):
        rows.append({"Nom*": f"IMPORT{run}{i}", "Postnom*": "MUKENDI", "Prénom*": first, "Sexe*": sex, "Classe*": klass, "Date naissance": date(2014, 3, i),
                     "Nom responsable": f"Mukendi {run}", "Téléphone responsable": f"+24381{run[-3:].encode().hex()[:4]}{i:03d}"[:16]})
    if bad:
        rows.append({"Nom*": f"ERREUR{run}", "Postnom*": "SANS", "Prénom*": "Classe", "Sexe*": "M", "Classe*": ""})
elif kind == "STAFF":
    cat = ref("Catégorie", "ENSEIGNANT")
    for i, (sex, last) in enumerate([("M", "KABONGO"), ("F", "NSIMBA")], 1):
        rows.append({"Matricule*": f"IMP{run}{i}", "Nom*": last, "Prénom*" if "Prénom*" in headers else "Prénom": "Agent", "Sexe": sex, "Catégorie*": cat,
                     "Téléphone": f"+24382000{i:04d}", "Date engagement": date(2020, 9, 1)})
    if bad:
        rows.append({"Matricule*": "", "Nom*": "SANSMATRICULE", "Catégorie*": cat})
else:
    # A real obligation of school C: the monthly tuition of the first pupil (the template has no fee list).
    year = ref("Année", "2026-2027"); fee = ref("Frais", "MINERVAL")
    # small amount on a rotating month: each run leaves a balance to regularise
    rows.append({"Année scolaire*": year, "Matricule élève*": "ELV-00001", "Frais*": fee, "Période": ["Janvier", "Février", "Mars", "Avril", "Mai"][sum(map(ord, run)) % 5], "Montant*": 500, "Devise*": "CDF",
                 "Date paiement*": date(2026, 9, 15), "Référence historique": f"HIST-{run}-1", "Observation": "Reprise cahier de caisse"})
    if bad:
        rows.append({"Année scolaire*": year, "Matricule élève*": "INCONNU-999", "Frais*": fee, "Montant*": 1000, "Devise*": "CDF", "Date paiement*": date(2026, 9, 15)})

for i, row in enumerate(rows, 6):
    for j, h in enumerate(headers, 1):
        if h in row:
            ws.cell(i, j, row[h])
wb.save(out)
print(f"{len(rows)} ligne(s) · colonnes {len(headers)} · référentiels {sorted(refs)[:4]}")
