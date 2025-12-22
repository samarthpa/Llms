import React, { useState } from 'react';
import './UrlInput.css';

const UrlInput = ({ onGenerate, onRegisterMonitoring, loading }) => {
  const [url, setUrl] = useState('');
  const [enableMonitoring, setEnableMonitoring] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!url.trim()) {
      alert('Please enter a valid URL');
      return;
    }

    try {
      new URL(url);
    } catch {
      alert('Please enter a valid URL (include http:// or https://)');
      return;
    }

    if (enableMonitoring) {
      onRegisterMonitoring(url);
    } else {
      onGenerate(url);
    }
  };

  return (
    <div className="url-input-container">
      <form onSubmit={handleSubmit} className="url-input-form">
        <div className="input-group">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Enter website URL (e.g., https://example.com)"
            className="url-input"
            disabled={loading}
          />
          <button type="submit" className="submit-button" disabled={loading}>
            {loading ? 'Processing...' : 'Generate llms.txt'}
          </button>
        </div>
        <div className="monitoring-option">
          <label>
            <input
              type="checkbox"
              checked={enableMonitoring}
              onChange={(e) => setEnableMonitoring(e.target.checked)}
              disabled={loading}
            />
            Enable ongoing monitoring (automatically update when website changes)
          </label>
        </div>
      </form>
    </div>
  );
};

export default UrlInput;


