"""
FastAPI REST API Server
Provides REST endpoints and WebSocket support for the network monitoring dashboard
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
import yaml

from database.db_connection import get_db, DatabaseConnection
from processor.pipeline import DeviceProcessor
from alerter.engine import AlertEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config_path = Path(__file__).parent.parent / "config.yaml"
with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Initialize FastAPI app
app = FastAPI(
    title="Network Monitor API",
    description="REST API for network monitoring and automation dashboard",
    version="1.0.0"
)

# CORS middleware
if config.get('api', {}).get('enable_cors', True):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.get('api', {}).get('cors_origins', ['*']),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Initialize components (with error handling)
try:
    db = get_db()
except Exception as e:
    logger.warning(f"Database connection failed: {e}. API will run in limited mode.")
    db = None

try:
    processor = DeviceProcessor(config_path)
except Exception as e:
    logger.warning(f"Processor initialization failed: {e}")
    processor = None

try:
    alerter = AlertEngine(config_path)
except Exception as e:
    logger.warning(f"Alerter initialization failed: {e}")
    alerter = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()


# Pydantic models
class DeviceResponse(BaseModel):
    device_id: int
    ip_address: str
    mac_address: Optional[str]
    vendor: Optional[str]
    hostname: Optional[str]
    device_type: Optional[str]
    risk_score: float
    status: Optional[str]
    response_time_ms: Optional[float]
    last_seen: datetime
    uptime_7d: Optional[float]
    uptime_30d: Optional[float]


class AnomalyResponse(BaseModel):
    anomaly_id: int
    device_id: Optional[int]
    ip_address: Optional[str]
    hostname: Optional[str]
    anomaly_type: str
    severity: str
    description: Optional[str]
    confidence: Optional[float]
    detected_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]


class AlertResponse(BaseModel):
    alert_id: int
    anomaly_id: Optional[int]
    device_id: Optional[int]
    alert_type: str
    severity: str
    channel: str
    message: str
    sent_at: datetime
    delivered: bool
    acknowledged_at: Optional[datetime]


class ScanRequest(BaseModel):
    subnet: str = Field(..., description="CIDR notation subnet to scan")
    interval: Optional[int] = Field(None, description="Scan interval in seconds (for continuous scanning)")


# API Endpoints

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "Network Monitor API",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if db is None:
        return {
            "status": "degraded",
            "database": "not_configured",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    db_healthy = db.health_check()
    
    return {
        "status": "healthy" if db_healthy else "degraded",
        "database": "connected" if db_healthy else "disconnected",
        "timestamp": datetime.utcnow().isoformat()
    }


# Device endpoints
@app.get("/api/devices", response_model=List[DeviceResponse])
async def get_devices(
    status: Optional[str] = Query(None, description="Filter by status: online, offline, degraded"),
    device_type: Optional[str] = Query(None, description="Filter by device type"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get list of devices"""
    if db is None:
        return []  # Return empty list instead of error for demo
    try:
        query = """
            SELECT * FROM device_current_status
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        if device_type:
            query += " AND device_type = %s"
            params.append(device_type)
        
        query += " ORDER BY last_seen DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            devices = cursor.fetchall()
        
        return [DeviceResponse(**dict(d)) for d in devices]
    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int):
    """Get device by ID"""
    if db is None:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM device_current_status WHERE device_id = %s
            """, (device_id,))
            device = cursor.fetchone()
            
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            
            return DeviceResponse(**dict(device))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching device: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/{device_id}/history")
async def get_device_history(
    device_id: int,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get device status history"""
    if db is None:
        return []
    try:
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    status_id,
                    status,
                    response_time_ms,
                    packet_loss_percent,
                    timestamp
                FROM device_status_history
                WHERE device_id = %s
                  AND timestamp >= NOW() - INTERVAL '%s hours'
                ORDER BY timestamp DESC
                LIMIT %s
            """, (device_id, hours, limit))
            history = cursor.fetchall()
        
        return [dict(h) for h in history]
    except Exception as e:
        logger.error(f"Error fetching device history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Anomaly endpoints
@app.get("/api/anomalies", response_model=List[AnomalyResponse])
async def get_anomalies(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get list of anomalies"""
    if db is None:
        return []
    try:
        query = """
            SELECT 
                a.anomaly_id,
                a.device_id,
                d.ip_address,
                d.hostname,
                a.anomaly_type,
                a.severity,
                a.description,
                a.confidence,
                a.detected_at,
                a.acknowledged_at,
                a.resolved_at
            FROM anomalies a
            LEFT JOIN devices d ON a.device_id = d.device_id
            WHERE 1=1
        """
        params = []
        
        if severity:
            query += " AND a.severity = %s"
            params.append(severity)
        
        if resolved is not None:
            if resolved:
                query += " AND a.resolved_at IS NOT NULL"
            else:
                query += " AND a.resolved_at IS NULL"
        
        query += " ORDER BY a.detected_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            anomalies = cursor.fetchall()
        
        return [AnomalyResponse(**dict(a)) for a in anomalies]
    except Exception as e:
        logger.error(f"Error fetching anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anomalies/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(anomaly_id: int, user: str = Query(..., description="User acknowledging the anomaly")):
    """Acknowledge an anomaly"""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE anomalies
                SET acknowledged_at = NOW(), acknowledged_by = %s
                WHERE anomaly_id = %s
            """, (user, anomaly_id))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Anomaly not found")
        
        return {"status": "acknowledged", "anomaly_id": anomaly_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging anomaly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/anomalies/{anomaly_id}/resolve")
async def resolve_anomaly(
    anomaly_id: int,
    notes: Optional[str] = Query(None, description="Resolution notes"),
    user: str = Query(..., description="User resolving the anomaly")
):
    """Resolve an anomaly"""
    try:
        with db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE anomalies
                SET resolved_at = NOW(), resolved_by = %s, resolution_notes = %s
                WHERE anomaly_id = %s
            """, (user, notes, anomaly_id))
            
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Anomaly not found")
        
        return {"status": "resolved", "anomaly_id": anomaly_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving anomaly: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alert endpoints
@app.get("/api/alerts", response_model=List[AlertResponse])
async def get_alerts(
    channel: Optional[str] = Query(None, description="Filter by channel"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledged status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get list of alerts"""
    if db is None:
        return []
    try:
        query = """
            SELECT 
                alert_id,
                anomaly_id,
                device_id,
                alert_type,
                severity,
                channel,
                message,
                sent_at,
                delivered,
                acknowledged_at
            FROM alerts
            WHERE 1=1
        """
        params = []
        
        if channel:
            query += " AND channel = %s"
            params.append(channel)
        
        if acknowledged is not None:
            if acknowledged:
                query += " AND acknowledged_at IS NOT NULL"
            else:
                query += " AND acknowledged_at IS NULL"
        
        query += " ORDER BY sent_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            alerts = cursor.fetchall()
        
        return [AlertResponse(**dict(a)) for a in alerts]
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, user: str = Query(..., description="User acknowledging the alert")):
    """Acknowledge an alert"""
    if alerter is None:
        raise HTTPException(status_code=503, detail="Alerter not available")
    success = alerter.acknowledge_alert(alert_id, user)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert")
    return {"status": "acknowledged", "alert_id": alert_id}


# Statistics endpoints
@app.get("/api/statistics")
async def get_statistics():
    """Get system statistics"""
    if db is None:
        return {
            "devices": {"total_devices": 0, "online_devices": 0, "offline_devices": 0},
            "anomalies": {"total_anomalies": 0, "active_anomalies": 0, "critical_anomalies": 0, "high_anomalies": 0},
            "alerts": {"total_alerts": 0, "unacknowledged_alerts": 0},
            "timestamp": datetime.utcnow().isoformat()
        }
    try:
        with db.get_cursor() as cursor:
            # Device statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_devices,
                    COUNT(*) FILTER (WHERE status = 'online') as online_devices,
                    COUNT(*) FILTER (WHERE status = 'offline') as offline_devices
                FROM device_current_status
            """)
            device_stats = cursor.fetchone()
            
            # Anomaly statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_anomalies,
                    COUNT(*) FILTER (WHERE resolved_at IS NULL) as active_anomalies,
                    COUNT(*) FILTER (WHERE severity = 'critical') as critical_anomalies,
                    COUNT(*) FILTER (WHERE severity = 'high') as high_anomalies
                FROM anomalies
            """)
            anomaly_stats = cursor.fetchone()
            
            # Alert statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_alerts,
                    COUNT(*) FILTER (WHERE acknowledged_at IS NULL) as unacknowledged_alerts
                FROM alerts
                WHERE sent_at >= NOW() - INTERVAL '24 hours'
            """)
            alert_stats = cursor.fetchone()
        
        return {
            "devices": dict(device_stats),
            "anomalies": dict(anomaly_stats),
            "alerts": dict(alert_stats),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and wait for client messages
            data = await websocket.receive_text()
            # Echo back or process client messages
            await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Background task to broadcast updates
async def broadcast_updates():
    """Background task to broadcast updates via WebSocket"""
    while True:
        if db is None:
            await asyncio.sleep(5)
            return
        try:
            # Check for new alerts
            with db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM alerts
                    WHERE sent_at >= NOW() - INTERVAL '1 minute'
                      AND acknowledged_at IS NULL
                """)
                result = cursor.fetchone()
                
                if result and result['count'] > 0:
                    await manager.broadcast({
                        "type": "new_alerts",
                        "count": result['count'],
                        "timestamp": datetime.utcnow().isoformat()
                    })
        except Exception as e:
            logger.error(f"Error in broadcast task: {e}")
        
        await asyncio.sleep(5)  # Check every 5 seconds


# Startup event
@app.on_event("startup")
async def startup_event():
    """Startup tasks"""
    logger.info("Starting Network Monitor API")
    asyncio.create_task(broadcast_updates())


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown tasks"""
    logger.info("Shutting down Network Monitor API")
    if db:
        db.close_pool()


# Mount static files if configured
if config.get('frontend', {}).get('serve_static', False):
    frontend_dir = Path(config.get('frontend', {}).get('build_dir', 'frontend/dist'))
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="static")


if __name__ == "__main__":
    api_config = config.get('api', {})
    uvicorn.run(
        "main:app",
        host=api_config.get('host', '0.0.0.0'),
        port=api_config.get('port', 8080),
        workers=api_config.get('workers', 4),
        reload=False
    )


