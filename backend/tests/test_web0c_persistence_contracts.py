from pathlib import Path

ROOT = Path(__file__).parents[1]
REPOS = (ROOT / "src" / "edusync" / "adapters" / "postgres_repositories.py").read_text(encoding="utf-8")
PLATFORM = (ROOT / "src" / "edusync" / "modules" / "platform" / "api" / "router.py").read_text(encoding="utf-8")
DEPS = (ROOT / "src" / "edusync" / "bootstrap" / "dependencies.py").read_text(encoding="utf-8")
COMPOSE = (ROOT.parent / "docker-compose.yml").read_text(encoding="utf-8")


def test_school_repository_uses_compare_and_swap_version():
    assert "WHERE id=:id AND version=:expected" in REPOS
    assert "version=version+1" in REPOS
    assert "OptimisticConcurrencyError" in REPOS


def test_platform_mutations_use_postgres_and_idempotency_header():
    assert "MemorySchoolRepository" not in PLATFORM
    assert "PostgresSchoolRepository" in PLATFORM
    assert "PostgresIdempotencyRepository" in PLATFORM
    assert 'alias="Idempotency-Key"' in PLATFORM
    assert 'scope_key="platform"' in PLATFORM


def test_permissions_are_reloaded_from_database_on_each_school_request():
    assert "memberships.permissions(membership.id)" in DEPS
    assert "claims.get(\"scope\") != \"school\"" in DEPS
    assert "tenant_transaction(school_id=school_id, user_id=user_id)" in DEPS


def test_compose_uses_one_shot_migrator_before_backend():
    assert "migrator:" in COMPOSE
    assert "service_completed_successfully" in COMPOSE
    assert "provision_database.py" in COMPOSE
    assert "bootstrap_platform_admin.py" in COMPOSE


def test_backend_container_does_not_receive_owner_or_bootstrap_password_secret():
    backend_block = COMPOSE.split("  backend:",1)[1].split("  frontend:",1)[0]
    assert "EDUSYNC_OWNER_DATABASE_URL" not in backend_block
    assert "EDUSYNC_PLATFORM_ADMIN_PASSWORD" not in backend_block
    assert "EDUSYNC_TENANT_DATABASE_URL" in backend_block
    assert "EDUSYNC_PLATFORM_DATABASE_URL" in backend_block


def test_platform_maps_database_uniqueness_races_to_http_409():
    assert "IntegrityError" in PLATFORM
    assert "status_code=409" in PLATFORM
