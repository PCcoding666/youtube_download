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
  credit_balance?: number;
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

// ==================== Credit 充值相关 ====================

export interface CreditPackage {
  usd_amount: number;
  credit_amount: number;
  label: string;
}

export interface CreditCheckoutResponse {
  success: boolean;
  checkout_url?: string;
  order_number?: string;
  sgd_amount: number;
  credit_amount: number;
  message: string;
}

export interface CreditBalance {
  credit_balance: number;
  username: string;
  user_id: number;
}

export interface CreditTransaction {
  id: number;
  type: string;
  amount: number;
  balance_after: number;
  description: string;
  order_number?: string;
  video_url?: string;
  created_at: string;
}

export interface CreditPackagesInfo {
  mode: string;
  currency: string;
  min_amount: number;
  suggested_amount: number;
  credits_per_sgd: number;
  rate: string;
  payment_configured: boolean;
  suggested_amounts: number[];
}

// 获取充值信息
export const getCreditPackages = async (): Promise<CreditPackagesInfo> => {
  const response = await api.get('/api/v1/credits/packages');
  return response.data;
};

// 创建充值 Checkout（自定义金额, SGD 整数）
export const createCreditCheckout = async (sgdAmount: number): Promise<CreditCheckoutResponse> => {
  const response = await api.post<CreditCheckoutResponse>('/api/v1/credits/checkout', { amount: sgdAmount });
  return response.data;
};

// 获取 Credit 余额
export const getCreditBalance = async (): Promise<CreditBalance> => {
  const response = await api.get<CreditBalance>('/api/v1/credits/balance');
  return response.data;
};

// 获取 Credit 交易记录
export const getCreditTransactions = async (limit: number = 50): Promise<{ credit_balance: number; transactions: CreditTransaction[] }> => {
  const response = await api.get(`/api/v1/credits/transactions?limit=${limit}`);
  return response.data;
};

// ==================== API Key 管理 ====================

export interface ApiKeyInfo {
  id: number;
  key_prefix: string;
  name: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface GenerateKeyResponse {
  success: boolean;
  api_key?: string;
  key_prefix?: string;
  name: string;
  message: string;
}

// 生成 API Key
export const generateApiKey = async (name?: string): Promise<GenerateKeyResponse> => {
  const response = await api.post<GenerateKeyResponse>('/api/v1/apikeys/generate', { name });
  return response.data;
};

// 列出 API Key
export const listApiKeys = async (): Promise<{ keys: ApiKeyInfo[]; count: number; max_keys: number }> => {
  const response = await api.get('/api/v1/apikeys/list');
  return response.data;
};

// 删除 API Key
export const deleteApiKey = async (keyId: number): Promise<{ success: boolean }> => {
  const response = await api.delete(`/api/v1/apikeys/${keyId}`);
  return response.data;
};

// 更新 API Key
export const updateApiKey = async (keyId: number, data: { name?: string; is_active?: boolean }): Promise<{ success: boolean }> => {
  const response = await api.put(`/api/v1/apikeys/${keyId}`, data);
  return response.data;
};

// ==================== 兼容旧版支付 API ====================

export type PlanType = 'free' | 'basic' | 'pro' | 'unlimited';
export type BillingCycle = 'monthly' | 'yearly';

export interface PaymentOrder {
  order_id: string;
  order_number: string;
  amount: number;
  status: string;
}

// 创建支付订单 (兼容旧版)
export const createPaymentOrder = async (plan: string, _billingCycle: BillingCycle = 'monthly'): Promise<PaymentOrder> => {
  // 映射旧版 plan 到充值金额
  const planToAmount: Record<string, number> = { basic: 5, pro: 10, unlimited: 20 };
  const amount = planToAmount[plan] || 5;
  const response = await api.post('/api/v1/credits/checkout', { usd_amount: amount });
  return { order_id: '', order_number: response.data.order_number || '', amount, status: 'pending' };
};

// 完成支付 (兼容旧版)
export const completePayment = async (_orderId: string): Promise<{ success: boolean }> => {
  return { success: true };
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
  agentgo_calls_total: number;
  agentgo_success_rate: number;
  agentgo_success_rate_total: number;
  
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
