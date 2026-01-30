import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api'

function AlertList() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadAlerts()
    const interval = setInterval(loadAlerts, 30000)
    return () => clearInterval(interval)
  }, [])

  const loadAlerts = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE}/alerts`)
      setAlerts(response.data)
      setError(null)
    } catch (err) {
      setError('Failed to load alerts')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const acknowledgeAlert = async (alertId) => {
    try {
      await axios.post(`${API_BASE}/alerts/${alertId}/acknowledge?user=admin`)
      loadAlerts()
    } catch (err) {
      console.error('Failed to acknowledge alert:', err)
    }
  }

  if (loading && alerts.length === 0) {
    return <div className="loading">Loading alerts...</div>
  }

  return (
    <div>
      <h2 style={{ marginBottom: '20px' }}>Alerts</h2>
      {error && <div className="error">{error}</div>}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Severity</th>
              <th>Channel</th>
              <th>Message</th>
              <th>Sent At</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map(alert => (
              <tr key={alert.alert_id}>
                <td>{alert.alert_type}</td>
                <td>
                  <span className={`severity-badge severity-${alert.severity}`}>
                    {alert.severity}
                  </span>
                </td>
                <td>{alert.channel}</td>
                <td>{alert.message}</td>
                <td>
                  {alert.sent_at 
                    ? new Date(alert.sent_at).toLocaleString()
                    : '-'
                  }
                </td>
                <td>
                  {alert.delivered ? '✓ Delivered' : '✗ Failed'}
                </td>
                <td>
                  {!alert.acknowledged_at && (
                    <button 
                      className="btn btn-primary"
                      onClick={() => acknowledgeAlert(alert.alert_id)}
                    >
                      Acknowledge
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default AlertList


