"""Rapport de la semaine / du mois — real HTTP + real PostgreSQL (owner, 2026-11-19).

A whole-school reader (promoteur) gets the letter with the money part; a préfet limited to the Secondaire gets his
section only, without the cash desks; the PDF is produced; the figures come from the database (direction fixture).

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/digest_report_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, school  # noqa: E402
import direction_report_postgres_integration as D  # noqa: E402

B = "/api/v1/finance/recovery/digest"


def run(A: dict) -> None:
    print("\n== Rapport de la semaine / du mois (19/11/2026)")
    D.fixture(A)
    sid = A["id"]
    p = as_(actor_for("PROMOTEUR", sid, extra={"finance.views.vf01.export"}))
    r = p.get(B + "?kind=MONTH&as_of=2026-11-14")
    j = r.json() if r.status_code == 200 else {}
    heads = [x["heading"] for x in j.get("paragraphs", [])]
    check("promoteur : lettre du mois lisible", r.status_code == 200 and j.get("title", "").startswith("Votre mois de novembre 2026"), r.text[:200])
    check("promoteur : l'argent, le recouvrement, les élèves, à surveiller", heads[1:] == ["L’argent", "Le recouvrement", "Les élèves", "À surveiller"], heads)
    rec = next((x["text"] for x in j.get("paragraphs", []) if x["heading"] == "Le recouvrement"), "")
    check("promoteur : taux et reste réels de l'école", "de ce qui était attendu est rentré" in rec and "Il reste" in rec, rec)
    pdf = as_(actor_for("PROMOTEUR", sid, extra={"finance.views.vf01.export"})).get(B + ".pdf?kind=WEEK")
    check("PDF de la semaine produit", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
    s = as_(actor_for("PREFET_ETUDES", sid, scope=("SECTION", "SECONDAIRE"), extra={"finance.views.vf01.export"}))
    r = s.get(B + "?kind=MONTH&as_of=2026-11-14")
    j = r.json() if r.status_code == 200 else {}
    heads = [x["heading"] for x in j.get("paragraphs", [])]
    check("préfet du Secondaire : sa section, sans les caisses", r.status_code == 200 and "L’argent" not in heads
          and "la section SECONDAIRE" in j["paragraphs"][0]["text"], j)
    pdf = as_(actor_for("PREFET_ETUDES", sid, scope=("SECTION", "SECONDAIRE"), extra={"finance.views.vf01.export"})).get(B + ".pdf?kind=MONTH")
    check("préfet : PDF de sa section produit", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code)
    no = as_(actor_for("INTENDANT", sid)).get(B)
    check("sans droit de recouvrement → refusé", no.status_code == 403, no.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
