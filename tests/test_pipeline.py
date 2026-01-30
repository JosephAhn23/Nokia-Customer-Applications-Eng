"""
Unit tests for data processing pipeline
"""

import pytest
import json
from datetime import datetime
from processor.pipeline import DeviceProcessor, InvalidScanError


@pytest.fixture
def processor():
    """Create a processor instance for testing"""
    return DeviceProcessor()


@pytest.fixture
def valid_scan_data():
    """Sample valid scan data"""
    return {
        "scan_id": "2026-02-01T14:30:00Z",
        "subnet": "192.168.1.0/24",
        "devices": [
            {
                "ip": "192.168.1.1",
                "mac": "00:11:22:33:44:55",
                "vendor": "Cisco Systems",
                "hostname": "router.local",
                "status": "online",
                "response_time_ms": 12.4,
                "open_ports": [22, 80, 443],
                "last_seen": "2026-02-01T14:30:00Z"
            }
        ],
        "metadata": {
            "scan_duration_seconds": 45.2,
            "devices_found": 1,
            "packet_loss_percent": 0.0
        }
    }


@pytest.fixture
def invalid_scan_data():
    """Sample invalid scan data"""
    return {
        "scan_id": "2026-02-01T14:30:00Z"
        # Missing required fields
    }


def test_validate_scan_valid(processor, valid_scan_data):
    """Test validation of valid scan data"""
    assert processor._validate_scan(valid_scan_data) == True


def test_validate_scan_invalid(processor, invalid_scan_data):
    """Test validation of invalid scan data"""
    assert processor._validate_scan(invalid_scan_data) == False


def test_validate_scan_missing_scan_id(processor):
    """Test validation fails when scan_id is missing"""
    data = {"subnet": "192.168.1.0/24", "devices": []}
    assert processor._validate_scan(data) == False


def test_process_scan_valid(processor, valid_scan_data):
    """Test processing of valid scan data"""
    result = processor.process_scan(valid_scan_data)
    assert result is not None
    assert len(result.enriched_devices) == 1
    assert 'analysis' in result.__dict__


def test_process_scan_invalid(processor, invalid_scan_data):
    """Test processing fails for invalid scan data"""
    with pytest.raises(InvalidScanError):
        processor.process_scan(invalid_scan_data)


def test_enrich_devices(processor, valid_scan_data):
    """Test device enrichment"""
    enriched = processor._enrich_devices(valid_scan_data['devices'])
    assert len(enriched) == 1
    assert 'device_type' in enriched[0]
    assert 'risk_score' in enriched[0]


def test_classify_device(processor):
    """Test device classification"""
    # Router
    device = {"vendor": "Cisco Systems", "open_ports": [22, 80]}
    assert processor._classify_device(device) == 'router'
    
    # Server
    device = {"open_ports": [22, 80, 443]}
    assert processor._classify_device(device) == 'server'
    
    # IoT
    device = {"open_ports": []}
    assert processor._classify_device(device) == 'iot_device'


def test_calculate_risk_score(processor):
    """Test risk score calculation"""
    device = {"open_ports": [22, 80, 443]}
    score = processor._calculate_risk_score(device)
    assert 0 <= score <= 100


def test_analyze_changes_new_device(processor, valid_scan_data):
    """Test anomaly detection for new device"""
    # First scan - should detect new device
    result = processor.process_scan(valid_scan_data)
    anomalies = result.analysis['anomalies']
    
    # Should have new_device anomaly
    new_device_anomalies = [a for a in anomalies if a['type'] == 'new_device']
    assert len(new_device_anomalies) > 0


def test_analyze_changes_port_opening(processor):
    """Test anomaly detection for port opening"""
    # Initial device state
    initial_scan = {
        "scan_id": "scan1",
        "subnet": "192.168.1.0/24",
        "devices": [{
            "ip": "192.168.1.1",
            "status": "online",
            "open_ports": [22, 80],
            "last_seen": datetime.utcnow().isoformat()
        }]
    }
    processor.process_scan(initial_scan)
    
    # New scan with additional port
    new_scan = {
        "scan_id": "scan2",
        "subnet": "192.168.1.0/24",
        "devices": [{
            "ip": "192.168.1.1",
            "status": "online",
            "open_ports": [22, 80, 3389],  # New port
            "last_seen": datetime.utcnow().isoformat()
        }]
    }
    result = processor.process_scan(new_scan)
    
    # Should detect new port anomaly
    port_anomalies = [a for a in result.analysis['anomalies'] if a['type'] == 'new_ports_opened']
    assert len(port_anomalies) > 0


def test_circuit_breaker(processor):
    """Test circuit breaker functionality"""
    cb = processor.circuit_breaker
    
    # Should start closed
    assert cb.state == "closed"
    
    # Simulate failures
    for _ in range(6):
        try:
            cb.call(lambda: exec('raise Exception("test")'))
        except:
            pass
    
    # Should be open after threshold
    assert cb.state == "open"


