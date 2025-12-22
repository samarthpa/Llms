import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:5001/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const generateLLMsTxt = async (url) => {
  const response = await api.post('/generate', { url });
  return response.data;
};

export const registerMonitoring = async (url, checkInterval = 86400) => {
  const response = await api.post('/monitor', { url, check_interval: checkInterval });
  return response.data;
};

export const stopMonitoring = async (websiteId) => {
  const response = await api.delete(`/monitor/${websiteId}`);
  return response.data;
};

export const getStatus = async (websiteId) => {
  const response = await api.get(`/status/${websiteId}`);
  return response.data;
};

export const downloadLLMsTxt = async (generationId) => {
  const response = await api.get(`/download/${generationId}`, {
    responseType: 'blob',
  });
  return response.data;
};

export const getMonitoredWebsites = async () => {
  const response = await api.get('/monitored');
  return response.data;
};

export const getChanges = async (websiteId, limit = 50) => {
  const response = await api.get(`/changes/${websiteId}`, {
    params: { limit },
  });
  return response.data;
};

export const triggerImmediateCheck = async (websiteId) => {
  const response = await api.post(`/monitor/${websiteId}/check`);
  return response.data;
};

export default api;


