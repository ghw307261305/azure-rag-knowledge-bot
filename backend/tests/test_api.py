from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Azure RAG Knowledge Bot API" in response.json()["message"]


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat() -> None:
    response = client.post("/api/chat", json={"question": "公開求人は削除できますか"})
    body = response.json()

    assert response.status_code == 200
    assert "モック回答" in body["answer"]
    assert len(body["citations"]) >= 1
    assert len(body["retrieved_chunks"]) >= 1

