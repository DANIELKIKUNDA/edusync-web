"""School identity as printed on documents (settings parity pass 3, 2026-10-24).

Desktop save_document_settings: signatory name / title and « show the school logo »; identity « devise / mention ».
Every PDF generator receives the same school dict; this helper adds the motto and the signatory and removes the logo key
when the school chose not to print it (logo_stream then returns None, exactly as for a school without logo).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text


def apply_document_preferences(conn, school: dict[str, Any]) -> dict[str, Any]:
    school_id = school.get("id")
    if not school_id:
        return school
    row = conn.execute(text("""SELECT s.motto, p.signatory_name, p.signatory_title, coalesce(p.show_school_logo, true) AS show_logo
          FROM schools s LEFT JOIN school_print_settings p ON p.school_id = s.id WHERE s.id = :sid"""), {"sid": str(school_id)}).mappings().first()
    if row is None:
        return school
    out = {**school, "motto": row["motto"], "signatory_name": row["signatory_name"], "signatory_title": row["signatory_title"]}
    if not row["show_logo"]:
        out["logo_object_key"] = None
    return out


def signatory_line(school: dict[str, Any]) -> str:
    """« Nom — Fonction », or an empty string when the school has not named a signatory."""
    return " — ".join(x.strip() for x in (school.get("signatory_name") or "", school.get("signatory_title") or "") if x and x.strip())
