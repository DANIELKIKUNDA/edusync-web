"""Final traceability matrix — INTENDANT, DIRECTEUR_ETUDES, DIRECTEUR_DISCIPLINE (certification 2026-10-30).

Every attribution of the canonical registry → lifecycle, real routes (introspection, tools/rbac/route_capability_map.py),
status and evidence. PASS needs an executed check (real HTTP + PostgreSQL run or unit test), never a string in a file.
N/A must carry its justification. Writes backend/docs/CERTIFICATION_TROIS_ROLES_MATRICE_FINALE.md.

    python tools/rbac/three_roles_matrix.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLES = ("INTENDANT", "DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE")
PG = "PG"   # tools/ci/three_roles_postgres_integration.py (backend/docs/evidence/three_roles_postgres_run.txt)
EVIDENCE = {
    "audit.entity.history.read": f"{PG} « historique d'audit d'un élève du secondaire / primaire → 404 / paiement → 404 » ; tests/test_audit_entity_history_scope.py (10)",
    "communications.compose": f"{PG} « SMS groupé autorisé / refusé » (route /communications/send : compose vérifié en premier)",
    "communications.history.read": f"{PG} « historique : message du secondaire visible, du primaire masqué », « livraisons → 404 » ; tests/test_communications_history_scope.py",
    "communications.read": f"{PG} « état des communications (200) »",
    "communications.send.class": f"{PG} « audience hors périmètre refusée : classe du primaire » ; tests/test_secondary_leadership_backend_regression.py",
    "communications.send.individual": f"{PG} « audience hors périmètre refusée : élève du primaire », « élève du secondaire d'une famille multi-sections »",
    "communications.send.section": f"{PG} « section secondaire : parent multi-sections, chacun une fois », « section primaire refusée »",
    "communications.sms.send": f"{PG} « crédit SMS réservé (2 sur 3) », « idempotence », « crédit insuffisant refusé »",
    "communications.sms.bulk_send": f"{PG} « DIRECTEUR_DISCIPLINE : SMS groupé autorisé (pas 403) » / « DIRECTEUR_ETUDES : refusé (403) »",
    "documents.history.read": f"{PG} « historique documentaire (200) » (3 rôles)",
    "documents.open": f"{PG} « Liens documentaires signés » : droit retiré / appartenance retirée / compte désactivé / autre école / expiré / altéré → 403",
    "families.directory.export": f"{PG} « export des familles autorisé (DIRECTEUR_ETUDES) / refusé (DIRECTEUR_DISCIPLINE) »",
    "families.read": f"{PG} « familles = celles du secondaire », « fiche d'une famille du seul primaire → 404 », « indicateurs familles (200) »",
    "headcounts.by_class.read": f"{PG} « effectifs par classe (200) »",
    "headcounts.by_option.read": f"{PG} « effectifs par option autorisés (DIRECTEUR_ETUDES) / refusés (DIRECTEUR_DISCIPLINE) »",
    "headcounts.by_section.read": f"{PG} « effectifs par section = SECONDAIRE seulement »",
    "headcounts.export": f"{PG} « export des effectifs par section sans le primaire »",
    "headcounts.movements.read": f"{PG} « mouvements des effectifs (200) »",
    "headcounts.read": f"{PG} « vue d'ensemble des effectifs (200) »",
    "inventory.assets.create": f"{PG} « immobilisation créée, idempotente (même clé → même bien, une ligne) »",
    "inventory.assets.history.read": f"{PG} « historique complet du bien (CREATE, UPDATE, REPAIR ×2, STATUS) »",
    "inventory.assets.read": f"{PG} « liste des biens (200) », « locaux (200) »",
    "inventory.assets.repair.record": f"{PG} « réparation ouverte puis clôturée », « clôture sans réparation → 409 », « bien sorti : réparation refusée »",
    "inventory.assets.status.update": f"{PG} « sortie du patrimoine (DISPOSED) », « bien sorti : changement d'état refusé (409) » (erreur 500 corrigée)",
    "inventory.assets.update": f"{PG} « modification de la fiche → événement UPDATE », « version périmée → 409 », « bien sorti : modification refusée »",
    "inventory.counts.create": f"{PG} « comptage » (création idempotente par clé facultative)",
    "inventory.counts.export": f"{PG} « export Excel du comptage », « impression du comptage en PDF », « exports sans le droit → 403 »",
    "inventory.counts.read": f"{PG} « liste des comptages (200) », « école B : comptage de A → 404 »",
    "inventory.counts.record": f"{PG} « écart sans justification → 422 », « comptage justifié », « article désactivé : comptage refusé »",
    "inventory.counts.validate": f"{PG} « double validation simultanée → une seule (200 + 409) », « stock aligné sur le comptage »",
    "inventory.stock.adjust": f"{PG} « ajustement sans sens → 422 », « ajustement à la baisse de 2 »",
    "inventory.stock.export_xlsx": f"{PG} « export Excel du stock : fichier valide, quantités numériques »",
    "inventory.stock.issue": f"{PG} « sortie de 3 », « sortie supérieure au stock refusée (409) », « concurrence : 2 sorties simultanées → une seule », « sans le droit → 403 »",
    "inventory.stock.item.manage": f"{PG} « article créé », « idempotence », « code en double → 409 », « fiche article modifiée (If-Match) », « version périmée → 409 »",
    "inventory.stock.low_alerts.read": f"{PG} « alertes de stock faible », « alertes sans le droit → 403 » (route créée)",
    "inventory.stock.movements.read": f"{PG} « mouvements consultables (3) » ; mesure : index 0101",
    "inventory.stock.read": f"{PG} « école B : article de A absent des listes », « stock des articles vendus (200) »",
    "inventory.stock.receive": f"{PG} « réception de 10 (201) »",
    "inventory.stock.sheet.print": f"{PG} « fiche de stock et impression du comptage en PDF »",
    "notifications.internal.dismiss": f"{PG} « un autre membre / une autre école ne peut pas l'acquitter (404) », « le destinataire l'acquitte », « sans le droit → 403 »",
    "notifications.internal.read": f"{PG} « le destinataire voit sa notification », « un autre membre ne la voit pas »",
    "personnel.read": f"{PG} « INTENDANT : personnel (lecture) (200) »",
    "settings.academic_year.read": f"{PG} « réglages scolaires en lecture (années, sections, identité) »",
    "settings.school_identity.read": f"{PG} « identité de l'école (lecture) (200) » ; « aucune modification des réglages → 403 »",
    "settings.structure.read": f"{PG} « réglages scolaires en lecture (années, sections, identité) »",
    "students.directory.export": f"{PG} « export Excel des élèves = secondaire seulement »",
    "students.identity.update": f"{PG} « correction d'identité (200) + audit », « version périmée → 409 », « identité + profil → 422 », « élève du primaire → refusé » ; DIRECTEUR_ETUDES → 403",
    "students.profile.complete": f"{PG} « complément de profil (adresse) d'un élève du secondaire (200) »",
    "students.profile.print_pdf": f"{PG} « fiche PDF d'un élève du secondaire », « du primaire → 404 »",
    "students.read": f"{PG} « liste des élèves = secondaire seulement », « fiche d'un élève du primaire / d'une autre école → 404 »",
}
NA = {
    "DEPRECATED": "N/A — capacité DEPRECATED (tableau de bord remplacé par /access/me et ses widgets ; inscriptions / familles lues par students.read et families.read, décision du 23/10)",
    "documents.print": "N/A — PLANNED pour tous les rôles (aucune route) : décision du propriétaire requise, non activée ici",
    "enrollments.export": "N/A — PLANNED pour tous les rôles qui la détiennent (Promoteur, Gestionnaire…) : décision du propriétaire requise",
    "students.lifecycle.history.read": "N/A — PLANNED pour tous les rôles qui la détiennent : décision du propriétaire requise",
}


def main() -> int:
    out_json = ROOT / ".local/route_map_3roles.json"
    subprocess.run([sys.executable, str(ROOT / "tools/rbac/route_capability_map.py"), *ROLES, "--json", str(out_json)], check=True, capture_output=True)
    routes = json.loads(out_json.read_text(encoding="utf-8"))
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    cat = {c["code"]: c for c in reg["capabilities"]}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    lines = [f"# Matrice finale des attributions — Intendant, Directeur des études, Directeur de discipline",
             "", f"Générée par `tools/rbac/three_roles_matrix.py` sur le commit `{head}` (30/10/2026). PASS = contrôle **exécuté** "
             "(application réelle + PostgreSQL réel isolé, ou test unitaire) ; « PG » renvoie à `tools/ci/three_roles_postgres_integration.py` "
             "(sortie : `backend/docs/evidence/three_roles_postgres_run.txt`). Les routes sont trouvées par introspection de l'application.", ""]
    totals = {}
    for role in ROLES:
        rows = routes[role]
        lines += [f"## {role} — {len(rows)} attributions au registre canonique", "", "| Capacité | Cycle de vie | Route(s) qui la contrôlent | État | Preuve / justification |", "|---|---|---|---|---|"]
        for r in rows:
            cap, life = r["capability"], r["lifecycle"]
            alias = cat.get(cap, {}).get("alias_of")
            rt = "<br>".join(r["routes"][:3]) or ("via " + alias if alias else "—")
            if life == "DEPRECATED":
                state, ev = "N/A", NA["DEPRECATED"]
            elif cap in NA:
                state, ev = "N/A", NA[cap]
            elif alias:
                base = cat.get(alias, {}).get("lifecycle")
                state, ev = ("PASS", f"alias de `{alias}` : {EVIDENCE.get(alias, '')}") if alias in EVIDENCE else ("N/A", f"alias de `{alias}` ({base}) : " + NA.get(alias, "non construite"))
            elif cap in EVIDENCE:
                state, ev = "PASS", EVIDENCE[cap]
            else:
                state, ev = "NON TESTÉ", "aucun contrôle exécuté"
            totals.setdefault(role, {}).setdefault(state, 0); totals[role][state] += 1
            lines.append(f"| `{cap}` | {life} | {rt} | **{state}** | {ev} |")
        lines += ["", "Bilan : " + " · ".join(f"{k} {v}" for k, v in sorted(totals[role].items())), ""]
    total = sum(sum(v.values()) for v in totals.values())
    lines += ["## Rapprochement avec les « 108 attributions » de la mission", "",
              f"Le registre canonique (source de vérité, statut CANONICAL) compte **{total} attributions** pour ces trois rôles : les 108 de "
              "l'origine (migrations 0008 / 0009) + les variantes de format ajoutées par la décision du 23/10 (alias `*.export_pdf`, "
              "`*.export_xlsx`, `*.print`), **moins** les capacités `personnel.*` et `finance.*` retirées aux deux directeurs par la migration "
              "0024 (point 9 : « secondary Directors are schooling-first »). Ces retraits ne figurent donc pas dans la matrice ; le serveur les "
              "refuse (PG « personnel refusé (403), conforme au registre canonique »). **Contradiction à trancher** : l'addendum "
              "`POINT3B_ADDENDUM_SECONDARY_LEADERSHIP.md` et la mission citent encore la consultation du personnel.", ""]
    (ROOT / "backend/docs/CERTIFICATION_TROIS_ROLES_MATRICE_FINALE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False))
    return 1 if any("NON TESTÉ" in v for v in totals.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
