"""Classes an actor may see for one capability (owner, 2026-11-17).

« L'interface ne doit jamais afficher une classe qui n'est pas de son périmètre » : a préfet, a directeur de section, a
directeur des études or de discipline given the finances sees only the classes of his scope, unless « toute l'école » is
chosen in Accès & rôles (SCHOOL scope). Same rule as the monthly recovery view: SCHOOL sees all; SECTION/CYCLE grants
match the section code, CLASS grants the class code; the grants are united, never widened.
"""
from __future__ import annotations


def visible_class_ids(driver_conn, school_id, scopes):
    """None = the whole school; otherwise the set of class ids (possibly empty) the scopes allow."""
    if not scopes or any(t == 'SCHOOL' for t, _ in scopes):
        return None
    sections = [str(v).upper() for t, v in scopes if t in ('SECTION', 'CYCLE') and v]
    classes = [str(v).upper() for t, v in scopes if t == 'CLASS' and v]
    if not sections and not classes:
        return set()
    with driver_conn.cursor() as c:
        c.execute("""SELECT sc.id FROM school_classes sc
                       JOIN school_sections ss ON ss.id=sc.section_id AND ss.school_id=sc.school_id
                      WHERE sc.school_id=%s AND (upper(ss.code)=ANY(%s) OR upper(sc.code)=ANY(%s))""",
                  (school_id, sections, classes))
        return {r[0] for r in c.fetchall()}


def scopes_union(actor, *capabilities):
    """Scopes of every capability the actor holds among `capabilities` (a screen reachable through several rights)."""
    out = []
    for cap in capabilities:
        if cap in actor.permissions:
            out.extend(actor.scopes_for(cap))
    return tuple(out)


def pupil_in_scope(conn, actor, capabilities, *, enrollment_id=None, student_id=None) -> bool:
    """True when the pupil (by enrollment or by student) belongs to a class the actor may see for these capabilities.
    `conn` is a SQLAlchemy connection of the tenant transaction."""
    from sqlalchemy import text
    v = visible_class_ids(conn.connection.driver_connection, actor.school_id, scopes_union(actor, *capabilities))
    if v is None:
        return True
    if not v:
        return False
    col, val = ('e.id', enrollment_id) if enrollment_id else ('e.student_id', student_id)
    return conn.execute(text(f"SELECT 1 FROM enrollments e WHERE e.school_id=:s AND {col}=:x AND e.class_id=ANY(CAST(:c AS uuid[])) LIMIT 1"),
                        {'s': str(actor.school_id), 'x': str(val), 'c': [str(x) for x in v]}).first() is not None
