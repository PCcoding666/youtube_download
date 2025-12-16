import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export type VideoResolution = '360' | '480' | '720' | '1080' | '1440' | '2160' | 'best' | 'audio';

export interface ProcessRequest {
  youtube_url: string;
  enable_transcription: boolean;
  resolution: VideoResolution;
}

export interface ProcessResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptSegment {
  text: string;
  start_time: number;
  end_time: number;
  speaker_id: number | null;
}

export interface TaskResult {
  task_id: string;
  status: string;
  video_url: string | null;
  audio_url: string | null;
  video_title: string | null;
  video_duration: number | null;
  transcript: TranscriptSegment[] | null;
  full_text: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface SystemInfo {
  ffmpeg_installed: boolean;
  oss_configured: boolean;
  transcription_enabled: boolean;
  proxy_configured: boolean;
}

export const processVideo = async (request: ProcessRequest): Promise<ProcessResponse> => {
  const response = await api.post<ProcessResponse>('/api/v1/process', request);
  return response.data;
};

export const getTaskStatus = async (taskId: string): Promise<TaskStatus> => {
  const response = await api.get<TaskStatus>(`/api/v1/status/${taskId}`);
  return response.data;
};

export const getTaskResult = async (taskId: string): Promise<TaskResult> => {
  const response = await api.get<TaskResult>(`/api/v1/result/${taskId}`);
  return response.data;
};

export const getSubtitleDownloadUrl = (taskId: string): string => {
  return `${API_BASE_URL}/api/v1/download/${taskId}/subtitle`;
};

export const getSystemInfo = async (): Promise<SystemInfo> => {
  const response = await api.get<SystemInfo>('/api/v1/system/info');
  return response.data;
};

export const healthCheck = async (): Promise<boolean> => {
  try {
    const response = await api.get('/api/v1/health');
    return response.data.status === 'healthy';
  } catch {
    return false;
  }
};

export default api;
