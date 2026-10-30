"""Section leadership: guard the actual server route implementation against scope regressions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHOOLING = (ROOT / "backend/src/edusync/modules/schooling/api/router.py").read_text(encoding="utf-8")
EFFECTIFS = (ROOT / "backend/src/edusync/modules/effectifs/api/router.py").read_text(encoding="utf-8")
MESSAGING = (ROOT / "backend/src/edusync/modules/communications/application/messaging.py").read_text(encoding="utf-8")
COMMUNICATIONS = (ROOT / "backend/src/edusync/modules/communications/api/router.py").read_text(encoding="utf-8")


def test_student_lifecycle_checks_scope_before_mutating():
    start = SCHOOLING.index("def _lifecycle(")
    end = SCHOOLING.index("@router.patch('/families/", start)
    body = SCHOOLING[start:end]
    assert "_need(actor,capability)" in body
    assert "scopes=_scopes(actor,capability)" in body
    assert "repo.get_student(actor.school_id,student_id,scopes=scopes)" in body
    assert "if not old: raise LookupError" in body
    assert body.index("repo.get_student(") < body.index("repo.change_status(")


def test_student_class_change_checks_source_and_target_section():
    start = SCHOOLING.index("def class_change(")
    end = SCHOOLING.index("@router.delete('/families/", start)
    body = SCHOOLING[start:end]
    assert "repo.get_student(actor.school_id,student_id,scopes=scopes)" in body
    assert "target=repo.class_info(actor.school_id,body.class_id)" in body
    assert "target.get('section_code')" in body
    assert "raise PermissionError('Classe cible hors de votre périmètre')" in body
    assert body.index("raise PermissionError('Classe cible hors") < body.index("repo.change_class(")


def test_headcount_exports_cannot_expand_read_scope():
    assert "Data scope is anchored to the read capability" in EFFECTIFS
    assert "scopes=_scopes(actor,group_cap)" in EFFECTIFS


def test_parent_messages_require_audience_specific_capability_and_scope():
    assert "'SCHOOL': 'communications.send.all_parents'" in COMMUNICATIONS
    assert "resolve_audience(c, actor, actor.school_id, b.audience_type, b.audience_ref, cap)" in COMMUNICATIONS
    assert "actor.scope_allows(cap, \"SECTION\"" in MESSAGING
    assert "raise PermissionError(\"Destinataires hors de votre périmètre de section\")" in MESSAGING
