import React from 'react'
import Statistics from './Statistics'

function Dashboard({ stats }) {
  return (
    <div>
      <h2 style={{ marginBottom: '20px' }}>Dashboard Overview</h2>
      <Statistics stats={stats} />
    </div>
  )
}

export default Dashboard


