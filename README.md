# Network Monitoring API 

A network monitoring API I built to demonstrate my understanding of API development, database design, and network monitoring concepts. This project shows foundational skills that I'm excited to apply and expand at Nokia.

For detailed API documentation and test results, see [Nokia Customer Applications Eng.pdf](Nokia%20Customer%20Applications%20Eng.pdf).

## Project Purpose

I built this to learn and demonstrate:
- FastAPI framework for building REST APIs
- PostgreSQL database design with connection pooling
- Network device discovery using ICMP and basic scanning
- Anomaly detection algorithms
- Database optimization with time-series partitioning
- Error handling and logging practices

## What This Demonstrates

### API Development
- 11 REST endpoints with proper error handling
- WebSocket support for real-time updates
- OpenAPI/Swagger auto-generated documentation
- Response times under 50ms for basic operations

### Database Skills
- PostgreSQL schema with 21 tables
- Time-series data partitioning
- Connection pooling (10-30 connections)
- Indexed queries for performance
- 3 views for efficient querying
- 44 database functions for automation

### Networking Concepts
- Device discovery and inventory management
- Status monitoring (online/offline/degraded)
- Response time tracking
- MAC address and vendor identification

### Python Development
- Clean, modular code structure
- Type hints and documentation
- Error handling throughout
- Logging and health checks

## What I Want to Learn at Nokia

I'm excited to work with Nokia's engineers to:
- Scale monitoring systems to enterprise level
- Integrate real network protocols (BGP, MPLS, SNMP)
- Implement production-grade network management
- Learn Nokia's network management tools and platforms
- Understand carrier-grade network operations
- Work with Nokia Service Router (SR) platforms

## System Components

1. **API Server** (`api/main.py`)
   - FastAPI-based REST API
   - WebSocket support for real-time updates
   - Health monitoring endpoints

2. **Data Processor** (`processor/`)
   - Processes network scan results
   - Enriches device data
   - Stores to database

3. **Alert Engine** (`alerter/`)
   - Multi-channel alerting (Email, Telegram, Dashboard)
   - Alert throttling and deduplication
   - Severity-based escalation

4. **Discovery Engine** (`discovery/`)
   - Network scanning with CIDR support
   - Parallel processing
   - Device detection

## Performance Metrics

- **Database queries**: <50ms average response time (tested with small dataset)
- **API endpoints**: <50ms average response time
- **Connection pool**: Handles 10-30 concurrent connections
- **Test data**: 5 devices loaded for demonstration

## Quick Start

### Prerequisites
- PostgreSQL 18+
- Python 3.10+
- Virtual environment

### Setup
```powershell
# Install PostgreSQL (if needed)
.\setup_postgresql.ps1

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Set database password
$env:NETMON_DB_PASSWORD="netmon123"

# Start API server
cd api
python main.py
```

### Access API
- **API Documentation**: http://localhost:8080/docs
- **Health Check**: http://localhost:8080/health
- **Devices**: http://localhost:8080/api/devices
- **Statistics**: http://localhost:8080/api/statistics

## Skills Demonstrated

This project showcases my ability to work with:
- **Python**: Advanced Python development with FastAPI
- **Databases**: PostgreSQL design and optimization
- **APIs**: RESTful service development
- **Networking**: Basic network monitoring concepts
- **Linux/Unix**: Scripting and system administration
- **Git**: Version control and collaboration

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/api/devices` | List network devices |
| GET | `/api/devices/{id}` | Get device details |
| GET | `/api/devices/{id}/history` | Device status history |
| GET | `/api/anomalies` | List detected anomalies |
| POST | `/api/anomalies/{id}/acknowledge` | Acknowledge anomaly |
| POST | `/api/anomalies/{id}/resolve` | Resolve anomaly |
| GET | `/api/alerts` | List alerts |
| POST | `/api/alerts/{id}/acknowledge` | Acknowledge alert |
| GET | `/api/statistics` | System statistics |

## Database Schema

- **21 tables**: Devices, anomalies, alerts, scans, baselines, etc.
- **3 views**: device_current_status, active_anomalies, device_statistics
- **44 functions**: Triggers, calculations, partition management
- **Time-series partitioning**: Monthly partitions for performance

## Limitations and Future Improvements

### Current Limitations
- Basic ICMP ping scanning (not production-grade protocols)
- Tested with small device count (5-100 devices)
- No integration with enterprise network management systems
- Basic anomaly detection (not machine learning-based)

### How I Would Scale This
If asked to scale this to Nokia's level, I would:
1. Implement connection pooling more aggressively
2. Add background workers for distributed scanning
3. Use Redis for caching and queue management
4. Implement horizontal scaling with load balancers
5. Add SNMP v3 for detailed device metrics
6. Integrate BGP monitoring for routing protocols
7. Use Netconf/YANG for configuration management
8. Implement telemetry streaming (gRPC, protobuf)

## Technology Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Database**: PostgreSQL 18 with connection pooling
- **API**: RESTful with WebSocket support
- **Networking**: ICMP scanning, device discovery
- **Scripting**: Python, Bash

## Project Structure

```
network-monitor/
├── api/              # FastAPI REST API
├── database/         # PostgreSQL schema and connection
├── processor/       # Data processing pipeline
├── alerter/         # Alert engine
├── discovery/       # Network discovery scripts
├── tests/           # Unit tests
└── config.yaml      # Configuration file
```

## Conclusion

This project demonstrates my foundational skills in API development, database design, and network monitoring concepts. I'm proud of what I've built as a learning project and excited to apply these concepts at Nokia's scale while learning from experienced engineers.

Built with Python, FastAPI, PostgreSQL, and Network Protocols. This is a learning project that demonstrates core skills I'm ready to expand at Nokia.
