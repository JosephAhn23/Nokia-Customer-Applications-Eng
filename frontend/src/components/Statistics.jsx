import React from 'react'

function Statistics({ stats }) {
  if (!stats) {
    return <div className="loading">Loading statistics...</div>
  }

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <div className="stat-value">{stats.devices?.total_devices || 0}</div>
        <div className="stat-label">Total Devices</div>
      </div>
      <div className="stat-card">
        <div className="stat-value" style={{ color: '#10b981' }}>
          {stats.devices?.online_devices || 0}
        </div>
        <div className="stat-label">Online Devices</div>
      </div>
      <div className="stat-card">
        <div className="stat-value" style={{ color: '#ef4444' }}>
          {stats.devices?.offline_devices || 0}
        </div>
        <div className="stat-label">Offline Devices</div>
      </div>
      <div className="stat-card">
        <div className="stat-value" style={{ color: '#f59e0b' }}>
          {stats.anomalies?.active_anomalies || 0}
        </div>
        <div className="stat-label">Active Anomalies</div>
      </div>
      <div className="stat-card">
        <div className="stat-value" style={{ color: '#dc2626' }}>
          {stats.anomalies?.critical_anomalies || 0}
        </div>
        <div className="stat-label">Critical Anomalies</div>
      </div>
      <div className="stat-card">
        <div className="stat-value" style={{ color: '#3b82f6' }}>
          {stats.alerts?.unacknowledged_alerts || 0}
        </div>
        <div className="stat-label">Unacknowledged Alerts</div>
      </div>
    </div>
  )
}

export default Statistics


