import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api'

function AnomalyList() {
  const [anomalies, setAnomalies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadAnomalies()
    const interval = setInterval(loadAnomalies, 30000)
    return () => clearInterval(interval)
  }, [])

  const loadAnomalies = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE}/anomalies?resolved=false`)
      setAnomalies(response.data)
      setError(null)
    } catch (err) {
      setError('Failed to load anomalies')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const acknowledgeAnomaly = async (anomalyId) => {
    try {
      await axios.post(`${API_BASE}/anomalies/${anomalyId}/acknowledge?user=admin`)
      loadAnomalies()
    } catch (err) {
      console.error('Failed to acknowledge anomaly:', err)
    }
  }

  if (loading && anomalies.length === 0) {
    return <div className="loading">Loading anomalies...</div>
  }

  return (
    <div>
      <h2 style={{ marginBottom: '20px' }}>Anomalies</h2>
      {error && <div className="error">{error}</div>}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Device</th>
              <th>Severity</th>
              <th>Description</th>
              <th>Detected</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {anomalies.map(anomaly => (
              <tr key={anomaly.anomaly_id}>
                <td>{anomaly.anomaly_type}</td>
                <td>{anomaly.ip_address || '-'}</td>
                <td>
                  <span className={`severity-badge severity-${anomaly.severity}`}>
                    {anomaly.severity}
                  </span>
                </td>
                <td>{anomaly.description || '-'}</td>
                <td>
                  {anomaly.detected_at 
                    ? new Date(anomaly.detected_at).toLocaleString()
                    : '-'
                  }
                </td>
                <td>
                  {!anomaly.acknowledged_at && (
                    <button 
                      className="btn btn-primary"
                      onClick={() => acknowledgeAnomaly(anomaly.anomaly_id)}
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

export default AnomalyList


