import React, { useState, useEffect } from 'react';
import { getMonitoredWebsites, getChanges, stopMonitoring, triggerImmediateCheck } from '../services/api';
import './MonitoringDashboard.css';

const MonitoringDashboard = () => {
  const [websites, setWebsites] = useState([]);
  const [selectedWebsite, setSelectedWebsite] = useState(null);
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadWebsites();
  }, []);

  const loadWebsites = async () => {
    try {
      setLoading(true);
      const data = await getMonitoredWebsites();
      setWebsites(data);
    } catch (error) {
      console.error('Error loading websites:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleWebsiteClick = async (website) => {
    setSelectedWebsite(website);
    try {
      const changeData = await getChanges(website.id);
      setChanges(changeData);
    } catch (error) {
      console.error('Error loading changes:', error);
    }
  };

  const handleStopMonitoring = async (websiteId) => {
    if (window.confirm('Are you sure you want to stop monitoring this website?')) {
      try {
        await stopMonitoring(websiteId);
        await loadWebsites();
        if (selectedWebsite && selectedWebsite.id === websiteId) {
          setSelectedWebsite(null);
          setChanges([]);
        }
      } catch (error) {
        console.error('Error stopping monitoring:', error);
        alert('Error stopping monitoring');
      }
    }
  };

  const handleImmediateCheck = async (websiteId) => {
    try {
      const result = await triggerImmediateCheck(websiteId);
      alert(result.changes_detected 
        ? `Changes detected! llms.txt updated to version ${result.latest_version}`
        : 'No changes detected. Website is up to date.');
      await loadWebsites();
      if (selectedWebsite && selectedWebsite.id === websiteId) {
        const changeData = await getChanges(websiteId);
        setChanges(changeData);
      }
    } catch (error) {
      console.error('Error triggering check:', error);
      alert('Error checking website');
    }
  };

  if (loading) {
    return <div className="dashboard-loading">Loading monitored websites...</div>;
  }

  if (websites.length === 0) {
    return (
      <div className="dashboard-empty">
        <p>No websites are currently being monitored.</p>
        <p>Enable monitoring when generating an llms.txt file to track changes automatically.</p>
      </div>
    );
  }

  return (
    <div className="monitoring-dashboard">
      <h2>Monitored Websites</h2>
      <div className="dashboard-content">
        <div className="websites-list">
          {websites.map((website) => (
            <div
              key={website.id}
              className={`website-item ${selectedWebsite?.id === website.id ? 'selected' : ''}`}
              onClick={() => handleWebsiteClick(website)}
            >
              <div className="website-info">
                <h3>{website.url}</h3>
                <div className="website-details">
                  <span className={`status-badge status-${website.status}`}>
                    {website.status}
                  </span>
                  <span>Pages: {website.pages_count}</span>
                  <span>Version: {website.latest_version || 'N/A'}</span>
                </div>
                {website.last_checked && (
                  <div className="last-checked">
                    Last checked: {new Date(website.last_checked).toLocaleString()}
                  </div>
                )}
              </div>
              <div className="website-actions">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleImmediateCheck(website.id);
                  }}
                  className="check-button"
                  title="Check for changes now"
                >
                  Check Now
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleStopMonitoring(website.id);
                  }}
                  className="stop-button"
                >
                  Stop Monitoring
                </button>
              </div>
            </div>
          ))}
        </div>
        {selectedWebsite && (
          <div className="changes-panel">
            <h3>Change History - {selectedWebsite.url}</h3>
            {changes.length === 0 ? (
              <p className="no-changes">No changes detected yet.</p>
            ) : (
              <div className="changes-list">
                {changes.map((change) => (
                  <div key={change.id} className="change-item">
                    <div className="change-header">
                      <span className={`change-type change-${change.change_type}`}>
                        {change.change_type.replace('_', ' ')}
                      </span>
                      <span className="change-date">
                        {new Date(change.detected_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="change-description">{change.description}</div>
                    {change.page_url && (
                      <div className="change-url">
                        <a href={change.page_url} target="_blank" rel="noopener noreferrer">
                          {change.page_url}
                        </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MonitoringDashboard;


