"""API endpoint tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["corpus_count"] > 0


def test_query_endpoint_basic(client):
    response = client.post("/api/query", json={"question": "نسيت أصلي", "top_k": 3})
    assert response.status_code == 200
    data = response.json()
    assert "query_original" in data
    assert "status" in data
    assert "candidates" in data
    assert data["query_original"] == "نسيت أصلي"


def test_query_endpoint_empty(client):
    response = client.post("/api/query", json={"question": "", "top_k": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REFER"
    assert len(data["candidates"]) == 0


def test_query_endpoint_sensitive(client):
    response = client.post("/api/query", json={"question": "زوجتي طلقت نفسها", "top_k": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REFER"
    assert data["sensitive_group"] is not None


def test_query_endpoint_top_k_limit(client):
    response = client.post("/api/query", json={"question": "الصلاة", "top_k": 10})
    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) <= 10


def test_query_endpoint_invalid_top_k(client):
    response = client.post("/api/query", json={"question": "الصلاة", "top_k": 0})
    assert response.status_code == 422


def test_query_endpoint_missing_question(client):
    response = client.post("/api/query", json={"top_k": 3})
    assert response.status_code == 422
