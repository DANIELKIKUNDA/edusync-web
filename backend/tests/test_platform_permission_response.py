from uuid import uuid4

from fastapi.testclient import TestClient

from edusync.bootstrap.app import create_app
from edusync.modules.platform.api.router import require_platform_actor
from edusync.shared.application.context import ActorContext


def test_collaborator_forbidden_routes_return_403_before_database_access():
    app = create_app()
    actor = ActorContext(
        user_id=uuid4(), school_id=None, membership_id=None,
        permissions=frozenset({'platform.schools.read', 'platform.audit.read', 'platform.health.read'}),
    )
    app.dependency_overrides[require_platform_actor] = lambda: actor
    with TestClient(app) as client:
        assert client.get('/api/v1/platform/system-notifications').status_code == 403
        response = client.post(
            f'/api/v1/platform/collaborators/{actor.user_id}/grant',
            json={'reason': 'Attempt to increase own permissions'},
        )
        assert response.status_code == 403
        assert 'platform.collaborators.manage' in response.json()['detail']
