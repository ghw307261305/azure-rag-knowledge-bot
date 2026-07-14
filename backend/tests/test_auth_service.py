import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.auth_service import create_local_token, decode_local_token
from app.services.config import get_settings
from main import app

client = TestClient(app)


@pytest.fixture()
def local_auth(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local_jwt")
    monkeypatch.setenv("LOCAL_JWT_SECRET", "local-test-secret-with-at-least-32-characters")
    monkeypatch.setenv("RAG_MODE", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _authorization(role: str, groups: list[str] | None = None) -> dict[str, str]:
    token = create_local_token("test-user", role=role, groups=groups or [])
    return {"Authorization": f"Bearer {token}"}


def test_local_token_round_trip(local_auth) -> None:
    token = create_local_token(
        "user-001",
        role="operator",
        groups=["finance-all", "risk"],
    )

    principal = decode_local_token(token)

    assert principal.subject == "user-001"
    assert principal.role == "operator"
    assert principal.groups == ("finance-all", "risk")


def test_expired_local_token_is_rejected(local_auth, monkeypatch) -> None:
    token = create_local_token("user-001", expires_in_seconds=1)
    monkeypatch.setattr("app.services.auth_service.time.time", lambda: 9_999_999_999)

    with pytest.raises(HTTPException) as error:
        decode_local_token(token)

    assert error.value.status_code == 401


def test_admin_endpoints_require_roles_when_local_auth_is_enabled(local_auth) -> None:
    assert client.get("/api/observability").status_code == 401
    assert client.get(
        "/api/observability", headers=_authorization("user")
    ).status_code == 403
    assert client.get(
        "/api/observability", headers=_authorization("operator")
    ).status_code == 200
    assert client.delete(
        "/api/observability", headers=_authorization("operator")
    ).status_code == 403
    assert client.delete(
        "/api/observability", headers=_authorization("admin")
    ).status_code == 200


def test_authenticated_memory_ownership_ignores_spoofed_client_id(local_auth) -> None:
    headers = _authorization("user", ["finance-all"])
    response = client.post(
        "/api/chat",
        headers=headers,
        json={
            "question": "请记住：我的部门是运营部",
            "client_id": "spoofed-client-id",
            "conversation_id": "conversation-auth-001",
        },
    )
    assert response.status_code == 200

    owned = client.get(
        "/api/memory",
        headers=headers,
        params={"client_id": "another-client-id"},
    )
    assert owned.status_code == 200
    assert owned.json()["client_id"] == "test-user"
    assert owned.json()["total"] == 1
