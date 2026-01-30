-- Network Monitor Database Schema
-- Optimized for time-series network data
-- PostgreSQL 14+

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Devices table - Master device registry
CREATE TABLE IF NOT EXISTS devices (
    device_id SERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    mac_address MACADDR,
    vendor VARCHAR(100),
    hostname VARCHAR(255),
    device_type VARCHAR(50),  -- router, server, printer, iot_device, unknown
    risk_score DECIMAL(5,2) DEFAULT 0,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_device UNIQUE(ip_address, mac_address)
);

-- Device status history - Time-series data (partitioned by month)
CREATE TABLE IF NOT EXISTS device_status_history (
    status_id BIGSERIAL,
    device_id INTEGER NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('online', 'offline', 'degraded')),
    response_time_ms DECIMAL(8,2),
    packet_loss_percent DECIMAL(5,2),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scan_id UUID NOT NULL,
    PRIMARY KEY (status_id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create partition for current month (example for February 2026)
CREATE TABLE IF NOT EXISTS device_status_history_y2026m02 
    PARTITION OF device_status_history
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Create partition for next month
CREATE TABLE IF NOT EXISTS device_status_history_y2026m03 
    PARTITION OF device_status_history
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- Port scan results
CREATE TABLE IF NOT EXISTS port_scan_results (
    scan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id INTEGER NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    open_ports INTEGER[] NOT NULL DEFAULT '{}',
    closed_ports INTEGER[] DEFAULT '{}',
    filtered_ports INTEGER[] DEFAULT '{}',
    scan_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scan_duration_ms INTEGER,
    nmap_version VARCHAR(50)
);

-- Create GIN index for array searches
CREATE INDEX IF NOT EXISTS idx_port_scan_open_ports_gin 
    ON port_scan_results USING GIN(open_ports);

-- Anomalies table
CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id BIGSERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(device_id) ON DELETE SET NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    description TEXT,
    confidence DECIMAL(3,2) CHECK (confidence >= 0 AND confidence <= 1),
    metadata JSONB,  -- Store additional anomaly-specific data
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),
    resolution_notes TEXT,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100)
);

-- Alerts table - Generated from anomalies
CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    anomaly_id INTEGER REFERENCES anomalies(anomaly_id) ON DELETE CASCADE,
    device_id INTEGER REFERENCES devices(device_id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    channel VARCHAR(20) NOT NULL,  -- email, telegram, dashboard, sms
    message TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered BOOLEAN DEFAULT FALSE,
    delivery_error TEXT,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    escalation_level INTEGER DEFAULT 0
);

-- Alert tracking for throttling and deduplication
CREATE TABLE IF NOT EXISTS alert_tracking (
    tracking_id BIGSERIAL PRIMARY KEY,
    alert_key VARCHAR(255) NOT NULL UNIQUE,  -- Composite key: device_id:anomaly_type
    first_occurrence TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_occurrence TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    last_alert_sent TIMESTAMPTZ,
    throttle_until TIMESTAMPTZ,
    resolved BOOLEAN DEFAULT FALSE
);

-- Scan metadata
CREATE TABLE IF NOT EXISTS scans (
    scan_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subnet CIDR NOT NULL,
    scan_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scan_completed_at TIMESTAMPTZ,
    scan_duration_seconds DECIMAL(8,2),
    devices_found INTEGER DEFAULT 0,
    devices_online INTEGER DEFAULT 0,
    devices_offline INTEGER DEFAULT 0,
    packet_loss_percent DECIMAL(5,2),
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    metadata JSONB
);

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================

-- Devices indexes
CREATE INDEX IF NOT EXISTS idx_devices_ip_address ON devices(ip_address);
CREATE INDEX IF NOT EXISTS idx_devices_mac_address ON devices(mac_address);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_devices_device_type ON devices(device_type);
CREATE INDEX IF NOT EXISTS idx_devices_risk_score ON devices(risk_score DESC);

-- Device status history indexes
CREATE INDEX IF NOT EXISTS idx_status_history_device_time 
    ON device_status_history(device_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_status_history_timestamp 
    ON device_status_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_status_history_status 
    ON device_status_history(status);
CREATE INDEX IF NOT EXISTS idx_status_history_scan_id 
    ON device_status_history(scan_id);

-- Port scan results indexes
CREATE INDEX IF NOT EXISTS idx_port_scan_device ON port_scan_results(device_id);
CREATE INDEX IF NOT EXISTS idx_port_scan_timestamp ON port_scan_results(scan_timestamp DESC);

-- Anomalies indexes
CREATE INDEX IF NOT EXISTS idx_anomalies_device ON anomalies(device_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_detected_at ON anomalies(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_type ON anomalies(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_anomalies_unresolved 
    ON anomalies(detected_at DESC) WHERE resolved_at IS NULL;

-- Alerts indexes
CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at ON alerts(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unacknowledged 
    ON alerts(sent_at DESC) WHERE acknowledged_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_channel ON alerts(channel);

-- Scans indexes
CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(scan_started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scans_subnet ON scans(subnet);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);

-- ============================================================================
-- FUNCTIONS AND TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at on devices
CREATE TRIGGER update_devices_updated_at 
    BEFORE UPDATE ON devices
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to automatically create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition()
RETURNS void AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    -- Create partition for next month
    start_date := date_trunc('month', CURRENT_DATE + interval '1 month');
    end_date := start_date + interval '1 month';
    partition_name := 'device_status_history_y' || to_char(start_date, 'YYYY') || 'm' || to_char(start_date, 'MM');
    
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF device_status_history FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        start_date,
        end_date
    );
END;
$$ LANGUAGE plpgsql;

-- Function to calculate device uptime
CREATE OR REPLACE FUNCTION calculate_device_uptime(p_device_id INTEGER, p_days INTEGER DEFAULT 7)
RETURNS DECIMAL(5,4) AS $$
DECLARE
    total_checks INTEGER;
    online_checks INTEGER;
    uptime DECIMAL(5,4);
BEGIN
    SELECT 
        COUNT(*),
        COUNT(*) FILTER (WHERE status = 'online')
    INTO total_checks, online_checks
    FROM device_status_history
    WHERE device_id = p_device_id
      AND timestamp >= NOW() - (p_days || ' days')::INTERVAL;
    
    IF total_checks = 0 THEN
        RETURN 0;
    END IF;
    
    uptime := online_checks::DECIMAL / total_checks::DECIMAL;
    RETURN uptime;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Current device status view
CREATE OR REPLACE VIEW device_current_status AS
SELECT 
    d.device_id,
    d.ip_address,
    d.mac_address,
    d.vendor,
    d.hostname,
    d.device_type,
    d.risk_score,
    d.last_seen,
    dsh.status,
    dsh.response_time_ms,
    dsh.packet_loss_percent,
    dsh.timestamp as last_status_check,
    calculate_device_uptime(d.device_id, 7) as uptime_7d,
    calculate_device_uptime(d.device_id, 30) as uptime_30d
FROM devices d
LEFT JOIN LATERAL (
    SELECT status, response_time_ms, packet_loss_percent, timestamp
    FROM device_status_history
    WHERE device_id = d.device_id
    ORDER BY timestamp DESC
    LIMIT 1
) dsh ON true;

-- Active anomalies view
CREATE OR REPLACE VIEW active_anomalies AS
SELECT 
    a.anomaly_id,
    a.device_id,
    d.ip_address,
    d.hostname,
    a.anomaly_type,
    a.severity,
    a.description,
    a.confidence,
    a.metadata,
    a.detected_at,
    a.acknowledged_at,
    a.resolved_at
FROM anomalies a
LEFT JOIN devices d ON a.device_id = d.device_id
WHERE a.resolved_at IS NULL
ORDER BY 
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END,
    a.detected_at DESC;

-- Device statistics view
CREATE OR REPLACE VIEW device_statistics AS
SELECT 
    d.device_id,
    d.ip_address,
    d.hostname,
    d.device_type,
    COUNT(DISTINCT dsh.scan_id) as total_scans,
    COUNT(*) FILTER (WHERE dsh.status = 'online') as online_count,
    COUNT(*) FILTER (WHERE dsh.status = 'offline') as offline_count,
    AVG(dsh.response_time_ms) FILTER (WHERE dsh.status = 'online') as avg_response_time_ms,
    MIN(dsh.response_time_ms) FILTER (WHERE dsh.status = 'online') as min_response_time_ms,
    MAX(dsh.response_time_ms) FILTER (WHERE dsh.status = 'online') as max_response_time_ms,
    COUNT(DISTINCT a.anomaly_id) as total_anomalies,
    COUNT(DISTINCT a.anomaly_id) FILTER (WHERE a.resolved_at IS NULL) as active_anomalies
FROM devices d
LEFT JOIN device_status_history dsh ON d.device_id = dsh.device_id
LEFT JOIN anomalies a ON d.device_id = a.device_id
GROUP BY d.device_id, d.ip_address, d.hostname, d.device_type;

-- ============================================================================
-- INITIAL DATA / SEED DATA (if needed)
-- ============================================================================

-- No seed data required - system will populate from scans

-- ============================================================================
-- BASELINE MANAGEMENT TABLES
-- ============================================================================

-- Device baselines for adaptive recalibration
CREATE TABLE IF NOT EXISTS device_baselines (
    baseline_id SERIAL PRIMARY KEY,
    device_ip INET NOT NULL,
    metric_type VARCHAR(50) NOT NULL,  -- response_time, packet_loss, throughput
    baseline_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_device_metric UNIQUE(device_ip, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_baselines_device ON device_baselines(device_ip);
CREATE INDEX IF NOT EXISTS idx_baselines_updated ON device_baselines(updated_at DESC);

-- Baseline recalibration logs
CREATE TABLE IF NOT EXISTS baseline_recalibration_logs (
    log_id BIGSERIAL PRIMARY KEY,
    device_ip INET NOT NULL,
    metric_type VARCHAR(50) NOT NULL,
    recalibration_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recalibration_logs_device ON baseline_recalibration_logs(device_ip, metric_type);
CREATE INDEX IF NOT EXISTS idx_recalibration_logs_created ON baseline_recalibration_logs(created_at DESC);

-- ============================================================================
-- INDEX MAINTENANCE TABLES
-- ============================================================================

-- Index health history
CREATE TABLE IF NOT EXISTS index_health_history (
    history_id BIGSERIAL PRIMARY KEY,
    index_name VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    fragmentation_percent DECIMAL(5,2),
    index_size_bytes BIGINT,
    scans_since_reset INTEGER,
    tuples_read BIGINT,
    tuples_fetched BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_history_index ON index_health_history(index_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_history_created ON index_health_history(created_at DESC);

-- Maintenance logs
CREATE TABLE IF NOT EXISTS maintenance_logs (
    log_id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,  -- index_maintenance, vacuum, analyze
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maintenance_logs_type ON maintenance_logs(event_type, created_at DESC);

-- Index maintenance schedule
CREATE TABLE IF NOT EXISTS index_maintenance_schedule (
    schedule_id SERIAL PRIMARY KEY,
    cron_pattern VARCHAR(50) NOT NULL,
    fragmentation_threshold DECIMAL(5,2) DEFAULT 30.0,
    max_duration INTERVAL DEFAULT '02:00:00',
    enabled BOOLEAN DEFAULT true,
    last_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- MEMORY MONITORING TABLES
-- ============================================================================

-- Memory events log
CREATE TABLE IF NOT EXISTS memory_events (
    event_id BIGSERIAL PRIMARY KEY,
    process_name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- leak_detected, recovery_action, etc.
    rss_mb DECIMAL(10,2),
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_events_process ON memory_events(process_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_events_type ON memory_events(event_type, created_at DESC);

-- ============================================================================
-- ARP DEFENSE TABLES
-- ============================================================================

-- ARP anomalies log
CREATE TABLE IF NOT EXISTS arp_anomalies (
    anomaly_id BIGSERIAL PRIMARY KEY,
    anomaly_type VARCHAR(50) NOT NULL,
    ip_address INET,
    mac_address MACADDR,
    details JSONB,
    severity VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arp_anomalies_ip ON arp_anomalies(ip_address, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_arp_anomalies_type ON arp_anomalies(anomaly_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_arp_anomalies_created ON arp_anomalies(created_at DESC);

-- ============================================================================
-- CHAOS ENGINEERING TABLES
-- ============================================================================

-- Chaos experiment results
CREATE TABLE IF NOT EXISTS chaos_experiments (
    experiment_id VARCHAR(100) PRIMARY KEY,
    experiment_name VARCHAR(100) NOT NULL,
    report_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chaos_experiments_name ON chaos_experiments(experiment_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chaos_experiments_created ON chaos_experiments(created_at DESC);

-- ============================================================================
-- GRANTS (adjust for your user)
-- ============================================================================

-- Create application user (run as postgres superuser)
-- CREATE USER netmon WITH PASSWORD 'your_secure_password';
-- GRANT CONNECT ON DATABASE netmon TO netmon;
-- GRANT USAGE ON SCHEMA public TO netmon;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO netmon;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO netmon;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO netmon;

