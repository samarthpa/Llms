import React, { useState } from 'react';
import UrlInput from './components/UrlInput';
import ResultDisplay from './components/ResultDisplay';
import MonitoringDashboard from './components/MonitoringDashboard';
import { generateLLMsTxt, registerMonitoring } from './services/api';
import './App.css';

function App() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('generate');

  const handleGenerate = async (url) => {
    setLoading(true);
    setError(null);
    try {
      const data = await generateLLMsTxt(url);
      setResult(data);
      setActiveTab('result');
    } catch (err) {
      setError(err.response?.data?.error || 'Error generating llms.txt. Please try again.');
      console.error('Generation error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterMonitoring = async (urlOrId) => {
    setLoading(true);
    setError(null);
    try {
      let data;
      if (typeof urlOrId === 'string') {
        data = await registerMonitoring(urlOrId);
        const genData = await generateLLMsTxt(urlOrId);
        setResult({ ...genData, monitoring_enabled: true });
        setActiveTab('result');
      } else {
        data = await registerMonitoring(result.url, 86400);
        setResult({ ...result, monitoring_enabled: true });
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Error registering monitoring. Please try again.');
      console.error('Monitoring registration error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>LLMs.txt Generator</h1>
        <p>Automatically generate and maintain llms.txt files for your website</p>
      </header>

      <nav className="App-nav">
        <button
          className={activeTab === 'generate' ? 'active' : ''}
          onClick={() => setActiveTab('generate')}
        >
          Generate
        </button>
        <button
          className={activeTab === 'monitor' ? 'active' : ''}
          onClick={() => setActiveTab('monitor')}
        >
          Monitoring Dashboard
        </button>
      </nav>

      <main className="App-main">
        {activeTab === 'generate' && (
          <div>
            <UrlInput
              onGenerate={handleGenerate}
              onRegisterMonitoring={handleRegisterMonitoring}
              loading={loading}
            />
            {error && <div className="error-message">{error}</div>}
            {result && <ResultDisplay result={result} onRegisterMonitoring={handleRegisterMonitoring} />}
          </div>
        )}

        {activeTab === 'monitor' && <MonitoringDashboard />}
      </main>

      <footer className="App-footer">
        <p>Built according to the <a href="https://llmstxt.org/" target="_blank" rel="noopener noreferrer">llms.txt specification</a></p>
      </footer>
    </div>
  );
}

export default App;


