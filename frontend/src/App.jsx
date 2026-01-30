import React, { useState, useEffect } from 'react'
import axios from 'axios'
import Dashboard from './components/Dashboard'
import DeviceList from './components/DeviceList'
import AnomalyList from './components/AnomalyList'
import AlertList from './components/AlertList'
import Statistics from './components/Statistics'
import './App.css'

const API_BASE = '/api'

function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [wsConnected, setWsConnected] = useState(false)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    // WebSocket connection
    const ws = new WebSocket(`ws://${window.location.host}/ws`)
    
    ws.onopen = () => {
      setWsConnected(true)
      console.log('WebSocket connected')
    }
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'new_alerts') {
        // Refresh alerts when new ones arrive
        console.log('New alerts received:', data.count)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setWsConnected(false)
    }
    
    ws.onclose = () => {
      setWsConnected(false)
      console.log('WebSocket disconnected')
    }

    // Load statistics
    loadStatistics()

    // Refresh statistics every 30 seconds
    const interval = setInterval(loadStatistics, 30000)

    return () => {
      ws.close()
      clearInterval(interval)
    }
  }, [])

  const loadStatistics = async () => {
    try {
      const response = await axios.get(`${API_BASE}/statistics`)
      setStats(response.data)
    } catch (error) {
      console.error('Error loading statistics:', error)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="container">
          <h1>Network Monitor Dashboard</h1>
          <div className="header-status">
            <span className={`status-indicator ${wsConnected ? 'connected' : 'disconnected'}`}>
              {wsConnected ? '● Connected' : '○ Disconnected'}
            </span>
          </div>
        </div>
      </header>

      <nav className="nav">
        <div className="container">
          <button 
            className={activeTab === 'dashboard' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button 
            className={activeTab === 'devices' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActiveTab('devices')}
          >
            Devices
          </button>
          <button 
            className={activeTab === 'anomalies' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActiveTab('anomalies')}
          >
            Anomalies
          </button>
          <button 
            className={activeTab === 'alerts' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setActiveTab('alerts')}
          >
            Alerts
          </button>
        </div>
      </nav>

      <main className="main">
        <div className="container">
          {activeTab === 'dashboard' && <Dashboard stats={stats} />}
          {activeTab === 'devices' && <DeviceList />}
          {activeTab === 'anomalies' && <AnomalyList />}
          {activeTab === 'alerts' && <AlertList />}
        </div>
      </main>
    </div>
  )
}

export default App


