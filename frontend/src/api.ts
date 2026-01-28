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

// New interfaces for direct URL extraction
export interface VideoFormatInfo {
  format_id: string;
  url: string;
  ext: string;
  resolution: string | null;
  height: number | null;
  width: number | null;
  fps: number | null;  // Can be float
  vcodec: string | null;
  acodec: string | null;
  filesize: number | null;
  tbr: number | null;
  format_note: string | null;
  is_video: boolean;
  is_audio: boolean;
  is_video_only: boolean;
  is_audio_only: boolean;
  has_both: boolean;
}

export interface DownloadURLs {
  video_url: string | null;
  audio_url: string | null;
  video_format: VideoFormatInfo | null;
  audio_format: VideoFormatInfo | null;
  needs_merge: boolean;
  resolution: string;
}

export interface ExtractedVideoInfo {
  video_id: string;
  title: string;
  duration: number;
  thumbnail: string | null;
  description: string | null;
  uploader: string | null;
  uploader_id: string | null;
  view_count: number | null;
  like_count: number | null;
  upload_date: string | null;
  format_count: number;
}

export interface ExtractURLRequest {
  youtube_url: string;
  resolution: VideoResolution;
}

export interface ExtractURLResponse {
  success: boolean;
  video_info: ExtractedVideoInfo | null;
  download_urls: DownloadURLs | null;
  all_formats: VideoFormatInfo[] | null;
  error_message: string | null;
  extraction_time: number | null;
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

// Direct URL extraction via AgentGo cloud browser (hides server IP)
export const extractDirectURLs = async (request: ExtractURLRequest): Promise<ExtractURLResponse> => {
  const response = await api.post<ExtractURLResponse>('/api/v1/extract/agentgo', request);
  return response.data;
};

// ==================== 用户认证相关 ====================

export interface RegisterRequest {
  email: string;
  password: string;
  username?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserInfo {
  id: string;
  email: string;
  username: string | null;
  created_at: string;
  is_premium?: boolean;
}

export interface AuthResponse {
  success: boolean;
  message: string;
  access_token: string;
  token_type: string;
  user: UserInfo;
}

export interface QuotaInfo {
  daily_limit: number;
  used_today: number;
  remaining: number;
  is_premium: boolean;
}

// Token 管理
const TOKEN_KEY = 'auth_token';

export const saveAuthToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
  api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
};

export const getAuthToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const clearAuthToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
  delete api.defaults.headers.common['Authorization'];
};

// 初始化时检查 token
const initToken = getAuthToken();
if (initToken) {
  api.defaults.headers.common['Authorization'] = `Bearer ${initToken}`;
}

// 用户注册
export const register = async (request: RegisterRequest): Promise<AuthResponse> => {
  const response = await api.post<AuthResponse>('/api/v1/auth/register', request);
  saveAuthToken(response.data.access_token);
  return response.data;
};

// 用户登录
export const login = async (request: LoginRequest): Promise<AuthResponse> => {
  const response = await api.post<AuthResponse>('/api/v1/auth/login', request);
  saveAuthToken(response.data.access_token);
  return response.data;
};

// 用户登出
export const logout = async (): Promise<void> => {
  try {
    await api.post('/api/v1/auth/logout');
  } finally {
    clearAuthToken();
  }
};

// 获取当前用户信息
export const getCurrentUser = async (): Promise<UserInfo | null> => {
  try {
    const response = await api.get<UserInfo>('/api/v1/auth/me');
    return response.data;
  } catch {
    return null;
  }
};

// 获取用户配额
export const getUserQuota = async (): Promise<QuotaInfo | null> => {
  try {
    const response = await api.get<QuotaInfo>('/api/v1/user/quota');
    return response.data;
  } catch {
    return null;
  }
};

// 检查匿名用户配额
export const checkAnonymousQuota = async (): Promise<QuotaInfo | null> => {
  try {
    const response = await api.get<QuotaInfo>('/api/v1/quota/anonymous');
    return response.data;
  } catch {
    return null;
  }
};

// ==================== 支付相关 ====================

export interface PaymentOrder {
  order_id: string;
  order_number: string;
  amount: number;
  status: string;
  qr_code_url?: string;
}

// 创建支付订单
export const createPaymentOrder = async (plan: string): Promise<PaymentOrder> => {
  const response = await api.post<PaymentOrder>('/api/v1/payment/create', { plan });
  return response.data;
};

// 完成支付
export const completePayment = async (orderId: string): Promise<{ success: boolean }> => {
  const response = await api.post<{ success: boolean }>('/api/v1/payment/complete', { order_id: orderId });
  return response.data;
};

export default api;
