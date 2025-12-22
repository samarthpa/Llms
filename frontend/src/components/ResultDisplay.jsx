import React, { useState } from 'react';
import { downloadLLMsTxt } from '../services/api';
import './ResultDisplay.css';

const ResultDisplay = ({ result, onRegisterMonitoring }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(result.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async () => {
    try {
      const blob = await downloadLLMsTxt(result.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `llms.txt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download error:', error);
      alert('Error downloading file');
    }
  };

  if (!result) {
    return null;
  }

  return (
    <div className="result-display-container">
      <div className="result-header">
        <h2>Generated llms.txt</h2>
        <div className="result-actions">
          <button onClick={handleCopy} className="action-button copy-button">
            {copied ? '✓ Copied!' : 'Copy'}
          </button>
          <button onClick={handleDownload} className="action-button download-button">
            Download
          </button>
          {!result.monitoring_enabled && result.website_id && (
            <button
              onClick={() => onRegisterMonitoring(result.website_id)}
              className="action-button monitor-button"
            >
              Enable Monitoring
            </button>
          )}
        </div>
      </div>
      <div className="result-info">
        <p>Version: {result.version} | Created: {new Date(result.created_at).toLocaleString()}</p>
      </div>
      <div className="result-content">
        <pre>{result.content}</pre>
      </div>
    </div>
  );
};

export default ResultDisplay;

