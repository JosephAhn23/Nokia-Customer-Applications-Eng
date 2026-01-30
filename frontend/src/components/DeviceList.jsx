import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api'

function DeviceList() {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadDevices()
    const interval = setInterval(loadDevices, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const loadDevices = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_BASE}/devices`)
      setDevices(response.data)
      setError(null)
    } catch (err) {
      setError('Failed to load devices')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading && devices.length === 0) {
    return <div className="loading">Loading devices...</div>
  }

  return (
    <div>
      <h2 style={{ marginBottom: '20px' }}>Devices</h2>
      {error && <div className="error">{error}</div>}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>IP Address</th>
              <th>Hostname</th>
              <th>Vendor</th>
              <th>Type</th>
              <th>Status</th>
              <th>Response Time</th>
              <th>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {devices.map(device => (
              <tr key={device.device_id}>
                <td>{device.ip_address}</td>
                <td>{device.hostname || '-'}</td>
                <td>{device.vendor || '-'}</td>
                <td>{device.device_type || 'unknown'}</td>
                <td>
                  <span className={`status-badge status-${device.status || 'offline'}`}>
                    {device.status || 'offline'}
                  </span>
                </td>
                <td>
                  {device.response_time_ms 
                    ? `${device.response_time_ms.toFixed(2)} ms`
                    : '-'
                  }
                </td>
                <td>
                  {device.last_seen 
                    ? new Date(device.last_seen).toLocaleString()
                    : '-'
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DeviceList


