"""Shared family mutations must not change other sections' household records."""
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from edusync.modules.schooling.api.router import _require_whole_family_scope


def test_shared_family_mutation_is_denied():
    school, family, own, foreign = (uuid4() for _ in range(4))
    repo = MagicMock()
    repo._visible_ids.return_value = {own}
    repo.connection.execute.return_value.all.return_value = [(own,), (foreign,)]
    with pytest.raises(PermissionError, match="Foyer partagé"):
        _require_whole_family_scope(repo, school, family, (("SECTION", "PRIMAIRE"),))


def test_family_mutation_allowed_when_all_children_visible():
    school, family, own = (uuid4() for _ in range(3))
    repo = MagicMock()
    repo._visible_ids.return_value = {own}
    repo.connection.execute.return_value.all.return_value = [(own,)]
    _require_whole_family_scope(repo, school, family, (("SECTION", "PRIMAIRE"),))


def test_schoolwide_mutation_skips_section_restriction():
    repo = MagicMock()
    _require_whole_family_scope(repo, uuid4(), uuid4(), (("SCHOOL", None),))
    repo.connection.execute.assert_not_called()


def test_family_mutation_routes_use_shared_family_guard():
    source = (Path(__file__).resolve().parents[1] /
              "src/edusync/modules/schooling/api/router.py").read_text(encoding="utf-8")
    for start, end in (("def patch_family(", "def add_guardian("),
                       ("def add_guardian(", "def class_change("),
                       ("def remove_guardian(", "def _school_identity(")):
        block = source.split(start, 1)[1].split(end, 1)[0]
        assert "_require_whole_family_scope(repo,actor.school_id,family_id,scopes)" in block
