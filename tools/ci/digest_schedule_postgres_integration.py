"""Rapports automatiques — real PostgreSQL (owner, 2026-11-19, étape 3).

The scheduler pass on a fixed « now »: Saturday 10:00 sends nothing; Saturday 20:30 sends the weekly report to the
whole-school responsible (PDF attached); a second pass sends nothing more; a report already sent with the button counts.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/digest_schedule_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import check, school  # noqa: E402
import direction_report_postgres_integration as D  # noqa: E402
import digest_send_postgres_integration as S  # noqa: E402
from edusync.modules.finance_recovery.application.digest_schedule import run_school  # noqa: E402


def run(A: dict) -> None:
    print("\n== Rapports automatiques (19/11/2026)")
    D.fixture(A)
    sid = A["id"]
    S.member(sid, "PROMOTEUR", "Promoteur")
    S.member(sid, "PREFET_ETUDES", "Prefet", ("SECTION", "SECONDAIRE"))
    services = H.APP.state.services
    check("samedi 10 h : rien ne part encore", run_school(services, sid, datetime(2026, 11, 21, 10, 0)) == [] and S.reports(sid) == [], S.reports(sid))
    done = run_school(services, sid, datetime(2026, 11, 21, 20, 30))
    got = S.reports(sid)
    check("samedi 20 h 30 : le rapport de la semaine part au promoteur, avec son PDF", done == ["WEEK"] and len(got) == 1 and bytes(got[0][2]) == b"%PDF", (done, got))
    check("un second passage n'envoie rien de plus", run_school(services, sid, datetime(2026, 11, 21, 20, 40)) == [] and len(S.reports(sid)) == 1, S.reports(sid))
    done = run_school(services, sid, datetime(2026, 11, 30, 20, 5))
    check("fin de mois : le rapport du mois part au promoteur et au préfet", done == ["MONTH"] and len(S.reports(sid)) == 3, (done, S.reports(sid)))


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
