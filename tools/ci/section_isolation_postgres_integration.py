"""Disposable real-PostgreSQL regression for school section directory isolation.

Run only after migrations on the localhost CI PostgreSQL service. All fixtures
are rolled back, including when an assertion fails.
"""
from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import create_engine, text
from edusync.adapters.postgres_schooling import PostgresSchoolingRepository

url = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
assert os.environ.get("CI") == "true", "Disposable CI only"
assert "127.0.0.1" in url or "localhost" in url, "Remote databases forbidden"

engine = create_engine(url, future=True)
school, year, family = (uuid4() for _ in range(3))
sections = {name: uuid4() for name in ("MATERNELLE", "PRIMAIRE", "SECONDAIRE")}
classes = {name: uuid4() for name in sections}
students = {name: uuid4() for name in sections}

with engine.connect() as conn:
    tx = conn.begin()
    try:
        for key in ("app.school_id", "app.current_school_id"):
            conn.execute(text("SELECT set_config(:key,:sid,true)"),
                         {"key": key, "sid": str(school)})
        conn.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'Section Isolation CI')"),
                     {"id": school, "code": f"SEC-{school.hex[:12]}"})
        conn.execute(text("""INSERT INTO academic_years
            (id,school_id,code,label,start_date,end_date,status)
            VALUES(:id,:s,'CI-SECTION','CI Section','2026-01-01','2026-12-31','ACTIVE')"""),
                     {"id": year, "s": school})
        conn.execute(text("""INSERT INTO families(id,school_id,code,display_name)
            VALUES(:id,:s,'SEC-F','Famille inter-sections')"""),
                     {"id": family, "s": school})
        for name in sections:
            conn.execute(text("""INSERT INTO school_sections(id,school_id,code,label)
                VALUES(:id,:s,:code,:label)"""),
                         {"id": sections[name], "s": school, "code": name, "label": name})
            conn.execute(text("""INSERT INTO school_classes
                (id,school_id,academic_year_id,section_id,code,label)
                VALUES(:id,:s,:y,:section,:code,:label)"""),
                         {"id": classes[name], "s": school, "y": year,
                          "section": sections[name], "code": f"CI-{name}",
                          "label": name})
            conn.execute(text("""INSERT INTO students
                (id,school_id,family_id,matricule,last_name,middle_name,first_name)
                VALUES(:id,:s,:f,:mat,'CI','SECTION',:name)"""),
                         {"id": students[name], "s": school, "f": family,
                          "mat": f"CI-{name}-{students[name].hex[:8]}", "name": name})
            conn.execute(text("""INSERT INTO enrollments
                (id,school_id,student_id,academic_year_id,class_id)
                VALUES(:id,:s,:student,:year,:klass)"""),
                         {"id": uuid4(), "s": school, "student": students[name],
                          "year": year, "klass": classes[name]})

        repo = PostgresSchoolingRepository(conn)
        for names in (("PRIMAIRE",), ("MATERNELLE",),
                      ("SECONDAIRE",), ("PRIMAIRE", "MATERNELLE")):
            grants = tuple(("SECTION", name) for name in names)
            expected = {students[name] for name in names}
            for all_years in (False, True):
                rows = repo.list_students(school, scopes=grants,
                                          all_years=all_years, limit=100)
                assert {row["id"] for row in rows} == expected, (
                    f"students scope={names} all_years={all_years}: {rows}")
            # Details must be denied outside the explicit section union.
            for section_name, student_id in students.items():
                detail = repo.get_student(school, student_id, scopes=grants)
                if section_name in names:
                    assert detail is not None, (names, section_name)
                    assert {e["section_code"] for e in detail["enrollments"]} == {section_name}
                else:
                    assert detail is None, (names, section_name)
            families = repo.list_families(school, scopes=grants,
                                         academic_year_id=year,
                                         enrolled_only=True)
            assert len(families) == 1, f"family scope={names}: {families}"
            assert int(families[0]["enrolled_children"]) == len(expected), (
                f"family count scope={names}: {families}")
        # A class-only grant must not require a non-existent section grant.
        class_grant = (("CLASS", "CI-PRIMAIRE"),)
        class_rows = repo.list_students(school, scopes=class_grant,
                                        all_years=True)
        assert {row["id"] for row in class_rows} == {students["PRIMAIRE"]}
        assert repo.get_student(school, students["PRIMAIRE"],
                                scopes=class_grant) is not None
        assert repo.get_student(school, students["MATERNELLE"],
                                scopes=class_grant) is None
        class_families = repo.list_families(school, scopes=class_grant,
                                           academic_year_id=year,
                                           enrolled_only=True)
        assert len(class_families) == 1
        assert int(class_families[0]["enrolled_children"]) == 1
        # A mixed class + section grant is an explicit union, not SCHOOL.
        mixed_grant = (("CLASS", "CI-PRIMAIRE"), ("SECTION", "MATERNELLE"))
        mixed_rows = repo.list_students(school, scopes=mixed_grant,
                                        all_years=True)
        assert {row["id"] for row in mixed_rows} == {
            students["PRIMAIRE"], students["MATERNELLE"]}
        mixed_families = repo.list_families(school, scopes=mixed_grant,
                                           academic_year_id=year,
                                           enrolled_only=True)
        assert len(mixed_families) == 1
        assert int(mixed_families[0]["enrolled_children"]) == 2
        # No grants must fail closed, including the shared-family directory.
        assert repo.list_students(school, scopes=(), all_years=True) == []
        assert repo.list_families(school, scopes=(),
                                  academic_year_id=year,
                                  enrolled_only=True) == []
        schoolwide = repo.list_students(school, scopes=(("SCHOOL", None),),
                                        all_years=True)
        assert {row["id"] for row in schoolwide} == set(students.values())
        print("PASS: real PostgreSQL section directory, shared family, dual grants")
    finally:
        tx.rollback()
engine.dispose()
