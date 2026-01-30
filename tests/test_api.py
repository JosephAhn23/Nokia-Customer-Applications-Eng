"""
API endpoint tests
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_health_endpoint():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data


def test_get_devices():
    """Test devices endpoint"""
    response = client.get("/api/devices?limit=10")
    # Should return 200 even if no devices
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_devices_with_filters():
    """Test devices endpoint with filters"""
    response = client.get("/api/devices?status=online&limit=10")
    assert response.status_code == 200


def test_get_statistics():
    """Test statistics endpoint"""
    response = client.get("/api/statistics")
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert "anomalies" in data
    assert "alerts" in data


def test_get_anomalies():
    """Test anomalies endpoint"""
    response = client.get("/api/anomalies?limit=10")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_alerts():
    """Test alerts endpoint"""
    response = client.get("/api/alerts?limit=10")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


