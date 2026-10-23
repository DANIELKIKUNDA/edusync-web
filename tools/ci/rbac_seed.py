"""CI seed for the RBAC migration proof (job `rbac-contract`): one school with a member per standard school role, a
member holding several roles, SECTION / CLASS scopes, a school-owned clone carrying export format variants and a
temporary exception grant. Runs on an ephemeral database BEFORE migration 0085; the snapshots before / after must be
identical (tools/ci/rbac_snapshot.py). Never used outside CI.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["EDUSYNC_OWNER_DATABASE_URL"])
with engine.begin() as c:
    school = c.execute(text("INSERT INTO schools(code,name,status) VALUES('CI-RBAC','École CI RBAC','ACTIVE') RETURNING id")).scalar_one()

    def member(n: int):
        uid = c.execute(text("INSERT INTO users(email,full_name,password_hash,active) VALUES(:e,:n,'x',true) RETURNING id"),
                        {"e": f"ci-rbac-{n}@example.test", "n": f"Membre CI {n}"}).scalar_one()
        mid = c.execute(text("INSERT INTO school_memberships(school_id,user_id,active) VALUES(:s,:u,true) RETURNING id"), {"s": school, "u": uid}).scalar_one()
        return uid, mid

    def assign(uid, mid, role_id, scopes=(("SCHOOL", None),)):
        aid = c.execute(text("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,granted_by_user_id,reason)
            VALUES(:u,:r,:s,:m,:u,'CI seed') RETURNING id"""), {"u": uid, "r": role_id, "s": school, "m": mid}).scalar_one()
        for t, v in scopes:
            c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)"), {"a": aid, "t": t, "v": v})

    roles = dict(c.execute(text("SELECT code,id FROM rbac_roles WHERE kind='SCHOOL_STANDARD' AND status='ACTIVE'")).all())
    n = 0
    for code, rid in sorted(roles.items()):
        n += 1
        uid, mid = member(n)
        if code in ("PREFET_ETUDES", "DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
            assign(uid, mid, rid, (("SECTION", "SECONDAIRE"),))
        elif code == "DIRECTION_SECTION":
            assign(uid, mid, rid, (("SECTION", "PRIMAIRE"),))
        else:
            assign(uid, mid, rid)
    n += 1
    uid, mid = member(n)                          # several roles on one member
    for code in ("CAISSIER", "SECRETARIAT", "INTENDANT"):
        assign(uid, mid, roles[code])
    n += 1
    uid, mid = member(n)                          # CLASS scope
    assign(uid, mid, roles["SECRETARIAT"], (("CLASS", "1A"),))
    clone = c.execute(text("""INSERT INTO rbac_roles(school_id,code,label,level,kind,status) VALUES(:s,'CUSTOM_CI','Clone CI','SCHOOL','SCHOOL_CUSTOM','ACTIVE')
        RETURNING id"""), {"s": school}).scalar_one()
    for cap in ("students.read", "students.directory.export_xlsx", "headcounts.read", "headcounts.print", "settings.work_year.select"):
        c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:c)"), {"r": clone, "c": cap})
    n += 1
    uid, mid = member(n)
    assign(uid, mid, clone)
    c.execute(text("""INSERT INTO rbac_exception_grants(user_id,school_id,membership_id,capability_code,scope_type,valid_until,granted_by_user_id,reason)
        VALUES(:u,:s,:m,'families.directory.print_pdf','SCHOOL',now()+interval '30 days',:u,'Exception CI temporaire')"""), {"u": uid, "s": school, "m": mid})
print(f"CI RBAC seed: {n} members")
