"""Loads the official referential into the shared ref_* tables (provisioning, owner connection). Idempotent: an
unchanged version (same checksum) is skipped; a changed one is rewritten in the same transaction. The files are
validated first (domain.referential.validate) and the database constraints check the weighting again."""
from __future__ import annotations

from sqlalchemy import text

from edusync.modules.pedagogy.domain.referential import CURRENT_VERSION, MAX_KEYS, Referential, load


def load_referential(conn, version: str = CURRENT_VERSION) -> str:
    ref: Referential = load(version)
    current = conn.execute(text("SELECT checksum FROM ref_programme_versions WHERE code=:v"), {"v": ref.version}).scalar()
    if current == ref.checksum:
        return f"Référentiel {ref.version} : déjà à jour"
    conn.execute(text("""INSERT INTO ref_sections(code,label,sort_order) VALUES(:code,:label,:order)
        ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, sort_order=EXCLUDED.sort_order"""), ref.sections)
    conn.execute(text("""INSERT INTO ref_options(code,sigle,label,option_group,sort_order) VALUES(:code,:sigle,:label,:group,:order)
        ON CONFLICT (code) DO UPDATE SET sigle=EXCLUDED.sigle, label=EXCLUDED.label, option_group=EXCLUDED.option_group,
          sort_order=EXCLUDED.sort_order"""), ref.options)
    conn.execute(text("""INSERT INTO ref_classes(code,label,section_code,option_code,level_order,cycle,structure)
        VALUES(:code,:label,:section,:option,:order,:cycle,:structure)
        ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, section_code=EXCLUDED.section_code, option_code=EXCLUDED.option_code,
          level_order=EXCLUDED.level_order, cycle=EXCLUDED.cycle, structure=EXCLUDED.structure"""), ref.classes)
    conn.execute(text("""INSERT INTO ref_courses(code,label) VALUES(:code,:label)
        ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label"""), ref.courses)
    conn.execute(text("""INSERT INTO ref_programme_versions(code,reference_year,published_on,checksum)
        VALUES(:v,:y,CAST(:d AS date),'')
        ON CONFLICT (code) DO NOTHING"""), {"v": ref.version, "y": ref.meta["reference_year"], "d": ref.meta["published_on"]})
    conn.execute(text("DELETE FROM ref_programme_lines WHERE version_code=:v"), {"v": ref.version})
    rows = []
    for p in ref.programmes:
        for line in p["lines"]:
            rows.append({"v": ref.version, "cls": p["class"], "course": line["course"], "order": line["order"],
                         "mandatory": line["mandatory"], "exam": line["exam"], "calculable": line["calculable"],
                         "semester": p["structure"] == "SEMESTRIEL", "domain": line["domain"], "subdomain": line["subdomain"],
                         **dict(zip(MAX_KEYS, line["max"]))})
    conn.execute(text(f"""INSERT INTO ref_programme_lines(version_code,class_code,course_code,sort_order,mandatory,has_exam,calculable,
          semester_structure,domain,subdomain,{','.join(MAX_KEYS)})
        VALUES(:v,:cls,:course,:order,:mandatory,:exam,:calculable,:semester,:domain,:subdomain,{','.join(':' + k for k in MAX_KEYS)})"""), rows)
    conn.execute(text("""UPDATE ref_programme_versions SET reference_year=:y, published_on=CAST(:d AS date), checksum=:c, loaded_at=now()
        WHERE code=:v"""), {"v": ref.version, "y": ref.meta["reference_year"], "d": ref.meta["published_on"], "c": ref.checksum})
    return (f"Référentiel {ref.version} : {len(ref.options)} options, {len(ref.classes)} classes, {len(ref.courses)} cours, "
            f"{len(ref.programmes)} programmes, {len(rows)} lignes")
