"""V2 lot 3a — teachers, titulars, conduct points licence (owner, 2026-11-22). Rules without a database;
tools/ci/pedagogy_teachers_postgres_integration.py proves them over real HTTP + PostgreSQL."""
import json
from pathlib import Path

import pytest

from edusync.modules.pedagogy.domain import conduct as cd

ROOT = Path(__file__).resolve().parents[2]
S = dict(late_rule_code="RETARD", late_threshold=5, late_penalty=5, alert_below=50)


def test_mentions_follow_the_parent_scale():
    assert [cd.mention(p)[0] for p in (100, 80, 79, 70, 69, 60, 59, 50, 49, 40, 39, 0)] == \
        ["E", "E", "TB", "TB", "B", "B", "AB", "AB", "ME", "ME", "MA", "MA"]
    with pytest.raises(cd.ConductError):
        cd.mention(101)


def test_conduct_is_computed_never_typed():
    assert cd.compute([], **S)["points"] == 100 and cd.compute([], **S)["mention"] == "E"
    facts = [{"code": "BAGARRE", "points": -15}, {"code": "INSOLENCE", "points": -10}]
    r = cd.compute(facts, **S)
    assert r["points"] == 75 and r["mention"] == "TB" and not r["to_follow"]
    assert cd.compute([{"code": "EXEMPLAIRE", "points": 5}], **S)["points"] == 100           # never above 100
    assert cd.compute([{"code": "FRAUDE", "points": -20}] * 6, **S)["points"] == 0            # never below 0


def test_repeated_lates_and_alert_threshold():
    lates = [{"code": "RETARD", "points": -2}] * 5
    r = cd.compute(lates, **S)
    assert r["lates"] == 5 and r["repeated_late_penalties"] == 1 and r["points"] == 100 - 10 - 5
    assert cd.compute(lates * 2, **S)["repeated_late_penalties"] == 2
    assert cd.compute(lates, **{**S, "late_threshold": 0})["repeated_late_penalties"] == 0      # rule switched off
    low = cd.compute([{"code": "BAGARRE", "points": -15}] * 4, **S)
    assert low["points"] == 40 and low["to_follow"] and low["mention"] == "ME"
    assert cd.compute([], adjustment=-30, **S)["points"] == 70                                  # discipline director's adjustment


def test_default_scale_and_validation():
    codes = [r.code for r in cd.DEFAULT_RULES]
    assert codes[0] == "RETARD" and {"BAGARRE", "FRAUDE"} == {r.code for r in cd.DEFAULT_RULES if r.grave}
    assert all(-50 <= r.points <= 20 and r.points != 0 for r in cd.DEFAULT_RULES)
    cd.check_rule("TELEPHONE", "Téléphone en classe", -3)
    for code, label, pts in (("", "Retard", -2), ("RETARD", "Re", -2), ("RETARD", "Retard", 0), ("RETARD", "Retard", -60), ("X Y", "Retard", -2)):
        with pytest.raises(cd.ConductError):
            cd.check_rule(code, label, pts)
    with pytest.raises(cd.ConductError):
        cd.check_settings(25, 5, 50)


def test_teacher_role_titulars_and_rights():
    sql = (ROOT / "backend/migrations/0126_pedagogy_teachers_conduct_scale.sql").read_text(encoding="utf-8")
    assert "('ENSEIGNANT','Enseignant'" in sql and "SCHOOL_STANDARD" in sql
    assert "class_id uuid PRIMARY KEY REFERENCES school_classes(id)" in sql            # one titular per class …
    assert "idx_pedagogy_titular_member" in sql and "UNIQUE (school_id, membership_id)" not in sql   # … several classes per teacher
    assert "DROP TABLE" not in sql.upper() and "ENABLE ROW LEVEL SECURITY" in sql
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    assert {"pedagogy.referential.read", "pedagogy.teaching.own.read"} <= set(reg["standard_roles"]["ENSEIGNANT"]["capabilities"])
    assert "pedagogy.conduct.configure" in reg["standard_roles"]["DIRECTEUR_DISCIPLINE"]["capabilities"]
    api = (ROOT / "backend/src/edusync/modules/pedagogy/api/teaching.py").read_text(encoding="utf-8")
    routes = api.count("@router.")
    assert api.count("Depends(require_pedagogy)") == routes and api.count("Depends(require_school_actor)") == routes
    assert 'AUTO_TITULAR_SECTIONS = ("MATERNELLE", "PRIMAIRE")' in api and "never deleted" in api
    titles = (ROOT / "backend/src/edusync/modules/access/domain/titles.py").read_text(encoding="utf-8")
    assert '"ENSEIGNANT": ("Enseignant", "Enseignante")' in titles


def test_two_courses_with_the_same_name_are_told_apart():
    from edusync.modules.pedagogy.api.teaching import _distinct_labels
    items = [{"label": "Expression Orale", "subdomain": "LANGUES CONGOLAISES"}, {"label": "Expression Orale", "subdomain": "FRANÇAIS"},
             {"label": "Religion", "subdomain": None}]
    _distinct_labels(items)
    assert [i["label"] for i in items] == ["Expression Orale (Langues congolaises)", "Expression Orale (Français)", "Religion"]
    assert all("subdomain" not in i for i in items)
