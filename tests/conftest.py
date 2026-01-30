"""
Pytest configuration and fixtures
"""

import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session")
def test_config():
    """Test configuration"""
    return {
        'database': {
            'host': os.getenv('TEST_DB_HOST', 'localhost'),
            'port': int(os.getenv('TEST_DB_PORT', 5432)),
            'name': os.getenv('TEST_DB_NAME', 'netmon_test'),
            'user': os.getenv('TEST_DB_USER', 'netmon'),
            'password': os.getenv('TEST_DB_PASSWORD', '')
        }
    }


