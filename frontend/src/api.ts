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

// Download video to server and upload to OSS (more reliable, no 403 issues)
export const extractDirectURLs = async (request: ExtractURLRequest): Promise<ExtractURLResponse> => {
  const response = await api.post<ExtractURLResponse>('/api/v1/extract', request);
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
  is_admin?: boolean;
}

export interface AuthResponse {
  success: boolean;
  message: string;
  token: string;
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
  saveAuthToken(response.data.token);
  return response.data;
};

// 用户登录
export const login = async (request: LoginRequest): Promise<AuthResponse> => {
  const response = await api.post<AuthResponse>('/api/v1/auth/login', request);
  saveAuthToken(response.data.token);
  return response.data;
};

// 用户登出
export const logout = async (): Promise<void> => {
  try {
    await api.get('/api/v1/auth/logout');
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

export type PlanType = 'free' | 'basic' | 'pro' | 'unlimited';
export type BillingCycle = 'monthly' | 'yearly';

export interface PricingPlan {
  id: PlanType;
  name: string;
  monthlyPrice: number;
  yearlyPrice: number;
  monthlyDownloads: number;
  maxResolution: string;
  features: string[];
}

export const PRICING_PLANS: Record<PlanType, PricingPlan> = {
  free: {
    id: 'free',
    name: '免费体验',
    monthlyPrice: 0,
    yearlyPrice: 0,
    monthlyDownloads: 3,
    maxResolution: '720p',
    features: ['每月3次下载', '720p画质', '基础速度'],
  },
  basic: {
    id: 'basic',
    name: '基础版',
    monthlyPrice: 29,
    yearlyPrice: 290,
    monthlyDownloads: 50,
    maxResolution: '1080p',
    features: ['每月50次下载', '1080p高清', '标准速度', '邮件支持'],
  },
  pro: {
    id: 'pro',
    name: '专业版',
    monthlyPrice: 69,
    yearlyPrice: 690,
    monthlyDownloads: 200,
    maxResolution: '4K',
    features: ['每月200次下载', '4K超清', '高速通道', '优先处理', '批量下载'],
  },
  unlimited: {
    id: 'unlimited',
    name: '无限版',
    monthlyPrice: 149,
    yearlyPrice: 999,
    monthlyDownloads: -1, // -1 表示无限
    maxResolution: '4K',
    features: ['无限次下载', '4K超清', '极速通道', '最高优先', 'API访问', '专属支持'],
  },
};

export interface PaymentOrder {
  order_id: string;
  order_number: string;
  amount: number;
  status: string;
  qr_code_url?: string;
  plan_type?: PlanType;
  billing_cycle?: BillingCycle;
}

// 创建支付订单
export const createPaymentOrder = async (plan: string, billingCycle: BillingCycle = 'monthly'): Promise<PaymentOrder> => {
  const response = await api.post<PaymentOrder>('/api/v1/payment/create', { plan, billing_cycle: billingCycle });
  return response.data;
};

// 完成支付
export const completePayment = async (orderId: string): Promise<{ success: boolean }> => {
  const response = await api.post<{ success: boolean }>('/api/v1/payment/complete', { order_id: orderId });
  return response.data;
};

// ==================== 管理员API ====================

export interface DashboardStats {
  // 下载统计
  total_requests_today: number;
  total_requests_week: number;
  total_requests_month: number;
  download_success_rate: number;
  avg_download_time: number;
  
  // AgentGo 统计
  agentgo_calls_today: number;
  agentgo_success_rate: number;
  
  // 流量统计（分类）
  total_traffic_bytes: number;
  download_traffic_bytes: number;
  proxy_traffic_bytes: number;
  agentgo_traffic_bytes: number;
  today_traffic_bytes: number;
  
  // 用户统计
  total_users: number;
  active_users_today: number;
  new_users_today: number;
  
  // 其他
  total_downloads: number;
  unique_videos: number;
}

export interface TrafficStats {
  total_bytes: number;
  download_bytes: number;
  proxy_bytes: number;
  agentgo_bytes: number;
  today_bytes: number;
  week_bytes: number;
  month_bytes: number;
  by_resolution: Record<string, number>;
  by_endpoint: Record<string, number>;
  daily_trend: Array<{ date: string; download_bytes: number; proxy_bytes: number }>;
  period_days: number;
}

export interface PopularVideo {
  video_title: string;
  video_url: string;
  download_count: number;
  total_bytes: number;
}

export interface DownloadStats {
  total_downloads: number;
  successful_downloads: number;
  failed_downloads: number;
  success_rate: number;
  avg_file_size: number;
  by_resolution: Record<string, number>;
  popular_videos: PopularVideo[];
  period_days: number;
}

export interface AgentGoStats {
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  success_rate: number;
  avg_duration: number;
  by_region: Record<string, number>;
  by_method: Record<string, number>;
  top_errors: Array<{ error: string; count: number }>;
  period_days: number;
}

export interface UserStats {
  total_users: number;
  premium_users: number;
  admin_users: number;
  new_users_period: number;
  daily_new_users: Array<{ date: string; count: number }>;
  period_days: number;
}

export interface GeoStats {
  by_country: Array<{ country_code: string; count: number; percentage: number }>;
  by_city: Array<{ city: string; count: number }>;
  period_days: number;
}

export interface TimelineData {
  data: Array<{ timestamp: string; api_requests: number; agentgo_calls: number }>;
  period_hours: number;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_premium: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface UsersListResponse {
  users: AdminUser[];
  total: number;
  limit: number;
  offset: number;
}

export interface LogEntry {
  id: number;
  endpoint?: string;
  method?: string;
  status_code?: number;
  response_time_ms?: number;
  ip_address?: string;
  country_code?: string;
  user_id?: number;
  region?: string;
  video_id?: string;
  success?: boolean;
  duration_seconds?: number;
  extraction_method?: string;
  error_message?: string;
  total_bytes?: number;
  resolution?: string;
  created_at: string;
}

// 管理员仪表盘
export const getAdminDashboard = async (): Promise<DashboardStats> => {
  const response = await api.get<DashboardStats>('/api/v1/admin/dashboard');
  return response.data;
};

// 流量统计
export const getTrafficStats = async (days: number = 7): Promise<TrafficStats> => {
  const response = await api.get<TrafficStats>(`/api/v1/admin/stats/traffic?days=${days}`);
  return response.data;
};

// AgentGo统计
export const getAgentGoStats = async (days: number = 7): Promise<AgentGoStats> => {
  const response = await api.get<AgentGoStats>(`/api/v1/admin/stats/agentgo?days=${days}`);
  return response.data;
};

// 下载统计
export const getDownloadStats = async (days: number = 7): Promise<DownloadStats> => {
  const response = await api.get<DownloadStats>(`/api/v1/admin/stats/downloads?days=${days}`);
  return response.data;
};

// 用户统计
export const getUserStats = async (days: number = 30): Promise<UserStats> => {
  const response = await api.get<UserStats>(`/api/v1/admin/stats/users?days=${days}`);
  return response.data;
};

// 地理分布
export const getGeoStats = async (days: number = 7): Promise<GeoStats> => {
  const response = await api.get<GeoStats>(`/api/v1/admin/stats/geo?days=${days}`);
  return response.data;
};

// 时间线
export const getTimelineStats = async (hours: number = 24): Promise<TimelineData> => {
  const response = await api.get<TimelineData>(`/api/v1/admin/stats/timeline?hours=${hours}`);
  return response.data;
};

// 用户列表
export const getAdminUsers = async (limit: number = 50, offset: number = 0): Promise<UsersListResponse> => {
  const response = await api.get<UsersListResponse>(`/api/v1/admin/users?limit=${limit}&offset=${offset}`);
  return response.data;
};

// 切换管理员权限
export const toggleUserAdmin = async (userId: number): Promise<{ success: boolean; is_admin: boolean }> => {
  const response = await api.post<{ success: boolean; is_admin: boolean }>(`/api/v1/admin/users/${userId}/toggle-admin`);
  return response.data;
};

// 获取日志
export const getRecentLogs = async (logType: 'api' | 'agentgo' | 'traffic', limit: number = 50): Promise<{ logs: LogEntry[]; type: string }> => {
  const response = await api.get<{ logs: LogEntry[]; type: string }>(`/api/v1/admin/recent-logs?log_type=${logType}&limit=${limit}`);
  return response.data;
};

export default api;
