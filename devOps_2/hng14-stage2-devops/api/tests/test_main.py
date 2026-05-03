import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

with patch("redis.Redis") as mock_redis_class:
    mock_r = MagicMock()
    mock_redis_class.return_value = mock_r
    from fastapi.testclient import TestClient
    from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job():
    mock_r.lpush.return_value = 1
    mock_r.hset.return_value = 1
    response = client.post("/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # valid UUID


def test_get_job_queued():
    mock_r.hget.return_value = b"queued"
    response = client.get("/jobs/some-uuid")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_job_completed():
    mock_r.hget.return_value = b"completed"
    response = client.get("/jobs/some-uuid")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_get_nonexistent_job():
    mock_r.hget.return_value = None
    response = client.get("/jobs/nonexistent")
    assert response.status_code == 404
