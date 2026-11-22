"""Follow-up of grade entry (V2 lot 3c, owner 2026-11-22: « encore plus de facilité »).

* missing(): for each teacher, the (class, course) of a period where present pupils still have no mark;
* remind(): one notification per teacher (bell rings), never twice the same day for the same text;
* automatic reminders: 3 days before a period's entry would normally stop (its end), the teachers who have not finished
  are reminded — called by the existing periodic evaluation (alerts.supervision), only for schools with the module.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text

from edusync.shared.infrastructure.realtime import note_inbox_changed

log = logging.getLogger(__name__)
COLUMN = {"P1": "max_p1", "P2": "max_p2", "EX1": "max_ex1", "P3": "max_p3", "P4": "max_p4", "EX2": "max_ex2", "P5": "max_p5", "P6": "max_p6", "EX3": "max_ex3"}
REMIND_DAYS_BEFORE_END = 3

MISSING_SQL = """
WITH present AS (
  SELECT e.class_id, count(*) AS n FROM enrollments e JOIN students st ON st.id=e.student_id
  WHERE e.school_id=:s AND e.academic_year_id=:y AND e.status IN ('VALIDATED','COMPLETED') AND st.status NOT IN ('ABANDON','TRANSFERRED')
  GROUP BY e.class_id),
graded AS (
  SELECT g.class_id, g.course_code, count(*) AS n FROM pedagogy_grades g JOIN students st ON st.id=g.student_id
  WHERE g.school_id=:s AND g.academic_year_id=:y AND g.period_code=:p AND g.status IS NOT NULL AND st.status NOT IN ('ABANDON','TRANSFERRED')
  GROUP BY g.class_id, g.course_code)
SELECT a.membership_id, m.user_id, c.id AS class_id, c.label AS class_label, a.course_code, k.label AS course_label,
       coalesce(pr.n,0) AS pupils, coalesce(gr.n,0) AS graded, l.has_exam,
       l.max_p1,l.max_p2,l.max_ex1,l.max_p3,l.max_p4,l.max_ex2,l.max_p5,l.max_p6,l.max_ex3
FROM pedagogy_teaching_assignments a
JOIN school_memberships m ON m.id=a.membership_id AND m.active
JOIN school_classes c ON c.id=a.class_id AND c.academic_year_id=:y
JOIN pedagogy_class_links lk ON lk.class_id=c.id JOIN ref_classes rc ON rc.code=lk.ref_class_code AND rc.structure=:t
JOIN pedagogy_programmes p ON p.school_id=c.school_id AND p.academic_year_id=c.academic_year_id AND p.ref_class_code=lk.ref_class_code AND p.status='VALIDATED'
JOIN pedagogy_programme_lines l ON l.programme_id=p.id AND l.course_code=a.course_code
JOIN ref_courses k ON k.code=a.course_code
LEFT JOIN present pr ON pr.class_id=c.id
LEFT JOIN graded gr ON gr.class_id=c.id AND gr.course_code=a.course_code
WHERE a.school_id=:s
ORDER BY c.label, l.sort_order"""


def missing(conn, school_id, year_id, structure: str, period: str) -> list[dict]:
    """Courses of the period with at least one present pupil without mark, grouped by teacher."""
    col = COLUMN[period]
    teachers: dict[str, dict] = {}
    for r in conn.execute(text(MISSING_SQL), {"s": str(school_id), "y": str(year_id), "p": period, "t": structure}).mappings():
        if int(r[col]) <= 0 or (period.startswith("EX") and not r["has_exam"]) or r["pupils"] == 0 or r["graded"] >= r["pupils"]:
            continue
        t = teachers.setdefault(str(r["membership_id"]), {"membership_id": str(r["membership_id"]), "user_id": str(r["user_id"]), "items": []})
        t["items"].append({"class_id": str(r["class_id"]), "class_label": r["class_label"], "course_code": r["course_code"],
                           "course_label": r["course_label"], "period": period, "missing": int(r["pupils"]) - int(r["graded"])})
    return list(teachers.values())


def remind(conn, school_id, teachers: list[dict], *, deadline: date | None = None) -> int:
    """One notification per teacher; the same text is never sent twice the same day."""
    sent = 0
    for t in teachers:
        lines = [f"{i['course_label']} — {i['class_label']} ({i['period']}) : {i['missing']} élève{'s' if i['missing'] > 1 else ''} sans cote" for i in t["items"][:12]]
        if len(t["items"]) > 12:
            lines.append(f"… et {len(t['items']) - 12} autre(s) cours")
        title = f"Cotes à compléter{f' avant le {deadline:%d/%m}' if deadline else ''}"
        body = "\n".join(lines)
        if conn.execute(text("""SELECT 1 FROM notifications WHERE school_id=:s AND user_id=:u AND category='PEDAGOGIE' AND title=:t AND body=:b
                AND created_at > now() - interval '1 day' LIMIT 1"""), {"s": str(school_id), "u": t["user_id"], "t": title, "b": body}).first():
            continue
        conn.execute(text("""INSERT INTO notifications(school_id,user_id,category,severity,title,body,link_path)
            VALUES(:s,:u,'PEDAGOGIE','INFO',:t,:b,'/pedagogie')"""), {"s": str(school_id), "u": t["user_id"], "t": title[:180], "b": body[:2000]})
        note_inbox_changed(t["user_id"], school_id)
        sent += 1
    return sent


def automatic_reminders(conn, school_id, today: date | None = None) -> int:
    """Periodic pass (alerts.supervision): for every validated calendar, a period whose end is within 3 days and whose
    entry is still open → remind the teachers who have not finished. Silent when nothing is due."""
    today = today or date.today()
    year = conn.execute(text("SELECT id FROM academic_years WHERE school_id=:s AND status='ACTIVE'"), {"s": str(school_id)}).scalar()
    if year is None:
        return 0
    rows = conn.execute(text("""SELECT k.structure,p.code,p.ends_on FROM pedagogy_calendars k JOIN pedagogy_calendar_periods p ON p.calendar_id=k.id
        WHERE k.school_id=:s AND k.academic_year_id=:y AND k.status='VALIDATED' AND p.entry_closed_at IS NULL
          AND p.ends_on BETWEEN :d AND :d2"""), {"s": str(school_id), "y": str(year), "d": today, "d2": today + timedelta(days=REMIND_DAYS_BEFORE_END)}).mappings().all()
    sent = 0
    for r in rows:
        sent += remind(conn, school_id, missing(conn, school_id, year, r["structure"], r["code"]), deadline=r["ends_on"])
    return sent
