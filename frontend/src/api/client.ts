import axios from 'axios';
import type { Config } from '../types/agent';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 minutes for long processing
});

export interface UploadResponse {
  filename: string;
  path: string;
}

export interface ProcessResponse {
  job_id: string;
}

export interface SystemStatus {
  ollama_connected: boolean;
  ollama_error: string | null;
  models: string[];
  decision_models: string[];
  embedding_models: string[];
  recommended_decision_model: string | null;
  recommended_embedding_model: string | null;
  knowledge_base_ready: boolean;
  flowchart_count: number;
  python_path: string;
  python_ready: boolean;
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const response = await api.get<SystemStatus>('/system-status');
  return response.data;
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post<UploadResponse>('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function deleteFile(filename: string): Promise<void> {
  await api.delete(`/upload/${encodeURIComponent(filename)}`);
}

export async function listFiles(): Promise<string[]> {
  const response = await api.get<{ files: string[] }>('/files');
  return response.data.files;
}

export interface FlowchartStatus {
  slug: string;
  name: string;
  local_stand: string | null;
  online_stand: string | null;
  onkopedia_url: string;
  status: 'current' | 'outdated' | 'unknown' | 'error';
  message: string | null;
}

export interface FlowchartStatusResponse {
  checked_at: string;
  flowcharts: FlowchartStatus[];
}

export async function checkFlowchartStatus(): Promise<FlowchartStatusResponse> {
  const response = await api.get<FlowchartStatusResponse>('/flowchart-status');
  return response.data;
}

export async function startProcessing(
  files: string[],
  config: Config
): Promise<ProcessResponse> {
  const response = await api.post<ProcessResponse>('/process', {
    llm_mode: config.llmMode,
    decision_model: config.decisionModel,
    use_flowchart: config.useFlowchart,
    use_historical_cases: config.useHistoricalCases,
    use_pubmed: config.usePubMed,
    use_conferences: config.useConferences,
    files,
  });
  return response.data;
}
