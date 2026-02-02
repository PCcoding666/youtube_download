import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BarChart3,
  Users,
  Activity,
  Globe,
  Clock,
  TrendingUp,
  Server,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  ArrowLeft,
  Shield,
  Database,
  Zap,
} from 'lucide-react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import {
  getAdminDashboard,
  getTrafficStats,
  getAgentGoStats,
  getDownloadStats,
  getUserStats,
  getGeoStats,
  getTimelineStats,
  getAdminUsers,
  getRecentLogs,
  toggleUserAdmin,
} from '../../api';
import type {
  DashboardStats,
  TrafficStats,
  AgentGoStats,
  DownloadStats,
  UserStats,
  GeoStats,
  TimelineData,
  AdminUser,
  LogEntry,
} from '../../api';
import LanguageSwitcher from '../LanguageSwitcher';
import './AdminDashboard.css';

interface AdminDashboardProps {
  onBack: () => void;
}

type TabType = 'overview' | 'traffic' | 'agentgo' | 'users' | 'logs';

const VALID_TABS: TabType[] = ['overview', 'traffic', 'agentgo', 'users', 'logs'];

const COLORS = ['#6366f1', '#8b5cf6', '#a855f7', '#d946ef', '#ec4899', '#f43f5e', '#f97316', '#eab308'];

// 从 URL hash 获取初始 tab
function getInitialTab(): TabType {
  const hash = window.location.hash.replace('#', '');
  if (VALID_TABS.includes(hash as TabType)) {
    return hash as TabType;
  }
  return 'overview';
}

function AdminDashboard({ onBack }: AdminDashboardProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabType>(getInitialTab);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // 数据状态
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const [traffic, setTraffic] = useState<TrafficStats | null>(null);
  const [agentgo, setAgentgo] = useState<AgentGoStats | null>(null);
  const [downloadStats, setDownloadStats] = useState<DownloadStats | null>(null);
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [geoStats, setGeoStats] = useState<GeoStats | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logType, setLogType] = useState<'api' | 'agentgo' | 'traffic'>('api');

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, trafficData, agentgoData, downloadData, userStatsData, geoData, timelineData] = await Promise.all([
        getAdminDashboard(),
        getTrafficStats(7),
        getAgentGoStats(7),
        getDownloadStats(7),
        getUserStats(30),
        getGeoStats(7),
        getTimelineStats(24),
      ]);
      
      setDashboard(dashboardData);
      setTraffic(trafficData);
      setAgentgo(agentgoData);
      setDownloadStats(downloadData);
      setUserStats(userStatsData);
      setGeoStats(geoData);
      setTimeline(timelineData);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('admin.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const response = await getAdminUsers(100, 0);
      setUsers(response.users);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('admin.loadUsersFailed'));
    }
  };

  const loadLogs = async (type: 'api' | 'agentgo' | 'traffic') => {
    try {
      const response = await getRecentLogs(type, 50);
      setLogs(response.logs);
    } catch (err: any) {
      setError(err.response?.data?.detail || t('admin.loadLogsFailed'));
    }
  };

  // 切换 tab 并更新 URL hash
  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
    window.location.hash = tab;
  };

  useEffect(() => {
    loadDashboardData();
    // 设置初始 hash（如果没有的话）
    if (!window.location.hash) {
      window.location.hash = 'overview';
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'users') {
      loadUsers();
    } else if (activeTab === 'logs') {
      loadLogs(logType);
    }
  }, [activeTab, logType]);

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  const handleToggleAdmin = async (userId: number) => {
    try {
      await toggleUserAdmin(userId);
      loadUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || t('admin.operationFailed'));
    }
  };

  if (loading) {
    return (
      <div className="admin-loading">
        <RefreshCw className="spinning" size={48} />
        <p>{t('admin.loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-error">
        <AlertTriangle size={48} />
        <p>{error}</p>
        <button onClick={loadDashboardData} className="retry-btn">
          <RefreshCw size={16} /> {t('common.retry')}
        </button>
      </div>
    );
  }

  const renderOverview = () => (
    <div className="overview-content">
      {/* 下载统计卡片 */}
      <div className="stats-grid">
        <div className="stat-card primary">
          <div className="stat-icon"><Activity size={24} /></div>
          <div className="stat-content">
            <span className="stat-value">{dashboard?.total_requests_today || 0}</span>
            <span className="stat-label">{t('admin.overview.todayDownloads')}</span>
          </div>
          <div className="stat-trend">
            <span className="trend-value">{t('common.week')}: {dashboard?.total_requests_week || 0} | {t('common.month')}: {dashboard?.total_requests_month || 0}</span>
          </div>
        </div>

        <div className="stat-card success">
          <div className="stat-icon"><CheckCircle size={24} /></div>
          <div className="stat-content">
            <span className="stat-value">{dashboard?.download_success_rate || 0}%</span>
            <span className="stat-label">{t('admin.overview.successRate')}</span>
          </div>
          <div className="stat-trend">
            <span className="trend-value">{t('admin.overview.totalDownloads')}: {dashboard?.total_downloads || 0}</span>
          </div>
        </div>

        <div className="stat-card info">
          <div className="stat-icon"><Zap size={24} /></div>
          <div className="stat-content">
            <span className="stat-value">{agentgo?.total_calls || 0}</span>
            <span className="stat-label">{t('admin.overview.agentgoCalls')}</span>
          </div>
          <div className="stat-trend">
            <span className="trend-value">{agentgo?.success_rate || 0}% {t('admin.overview.successRate')}</span>
          </div>
        </div>

        <div className="stat-card warning">
          <div className="stat-icon"><Users size={24} /></div>
          <div className="stat-content">
            <span className="stat-value">{dashboard?.total_users || 0}</span>
            <span className="stat-label">{t('admin.overview.totalUsers')}</span>
          </div>
          <div className="stat-trend">
            <span className="trend-value">{t('admin.overview.newToday')}: {dashboard?.new_users_today || 0} | {t('admin.overview.activeToday')}: {dashboard?.active_users_today || 0}</span>
          </div>
        </div>
      </div>

      {/* 流量分类统计 */}
      <div className="traffic-breakdown">
        <h3><Database size={20} /> {t('admin.traffic.breakdown')}</h3>
        <div className="traffic-cards">
          <div className="traffic-card download">
            <span className="traffic-label">{t('admin.traffic.downloadTraffic')}</span>
            <span className="traffic-value">{formatBytes(dashboard?.download_traffic_bytes || 0)}</span>
            <span className="traffic-sub">{t('admin.traffic.today')}: {formatBytes(dashboard?.today_traffic_bytes || 0)}</span>
          </div>
          <div className="traffic-card proxy">
            <span className="traffic-label">{t('admin.traffic.proxyTraffic')}</span>
            <span className="traffic-value">{formatBytes(dashboard?.proxy_traffic_bytes || 0)}</span>
            <span className="traffic-sub">{t('admin.traffic.proxyNote')}</span>
          </div>
          <div className="traffic-card agentgo">
            <span className="traffic-label">{t('admin.traffic.agentgoTraffic')}</span>
            <span className="traffic-value">{formatBytes(dashboard?.agentgo_traffic_bytes || 0)}</span>
            <span className="traffic-sub">{t('admin.traffic.agentgoNote')}</span>
          </div>
          <div className="traffic-card total">
            <span className="traffic-label">{t('admin.traffic.totalTraffic')}</span>
            <span className="traffic-value">{formatBytes(dashboard?.total_traffic_bytes || 0)}</span>
            <span className="traffic-sub">{t('admin.traffic.uniqueVideos')}: {dashboard?.unique_videos || 0}</span>
          </div>
        </div>
      </div>

      {/* 时间线图表 */}
      <div className="chart-section">
        <h3><Clock size={20} /> {t('admin.overview.trend24h')}</h3>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={timeline?.data || []}>
              <defs>
                <linearGradient id="colorApi" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorAgentgo" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis 
                dataKey="timestamp" 
                stroke="#94a3b8"
                tickFormatter={(value) => new Date(value).getHours() + ':00'}
              />
              <YAxis stroke="#94a3b8" />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Legend />
              <Area type="monotone" dataKey="api_requests" name={t('admin.overview.todayDownloads')} stroke="#6366f1" fillOpacity={1} fill="url(#colorApi)" />
              <Area type="monotone" dataKey="agentgo_calls" name="AgentGo" stroke="#8b5cf6" fillOpacity={1} fill="url(#colorAgentgo)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 地理分布 */}
      <div className="chart-section">
        <h3><Globe size={20} /> {t('admin.overview.geoDistribution')}</h3>
        <div className="geo-grid">
          <div className="geo-chart">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={geoStats?.by_country?.slice(0, 8) || []}
                  dataKey="count"
                  nameKey="country_code"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, percent }) => `${name} (${((percent || 0) * 100).toFixed(0)}%)`}
                >
                  {geoStats?.by_country?.slice(0, 8).map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="geo-list">
            <h4>{t('admin.overview.hotCities')}</h4>
            <ul>
              {geoStats?.by_city?.slice(0, 8).map((city, i) => (
                <li key={i}>
                  <span className="city-name">{city.city}</span>
                  <span className="city-count">{city.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );

  const renderTraffic = () => (
    <div className="traffic-content">
      {/* 流量分类统计 */}
      <div className="stats-row">
        <div className="stat-card">
          <h4>{t('admin.traffic.downloadTraffic')}</h4>
          <span className="big-value">{formatBytes(traffic?.download_bytes || 0)}</span>
          <span className="stat-sub">{t('admin.traffic.today')}: {formatBytes(traffic?.today_bytes || 0)}</span>
        </div>
        <div className="stat-card">
          <h4>{t('admin.traffic.proxyTraffic')}</h4>
          <span className="big-value">{formatBytes(traffic?.proxy_bytes || 0)}</span>
          <span className="stat-sub">{t('admin.traffic.proxyNote')}</span>
        </div>
        <div className="stat-card">
          <h4>{t('admin.traffic.agentgoTraffic')}</h4>
          <span className="big-value">{formatBytes(traffic?.agentgo_bytes || 0)}</span>
          <span className="stat-sub">{t('admin.traffic.agentgoNote')}</span>
        </div>
        <div className="stat-card highlight">
          <h4>{t('admin.traffic.totalTraffic')}</h4>
          <span className="big-value">{formatBytes(traffic?.total_bytes || 0)}</span>
          <span className="stat-sub">{t('common.week')}: {formatBytes(traffic?.week_bytes || 0)}</span>
        </div>
      </div>

      {/* 流量趋势图 */}
      <div className="chart-section">
        <h3><TrendingUp size={20} /> {t('admin.traffic.dailyTrend')}</h3>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={traffic?.daily_trend || []}>
              <defs>
                <linearGradient id="colorDownload" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorProxy" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" tickFormatter={(v) => formatBytes(v)} />
              <Tooltip 
                formatter={(value) => formatBytes(Number(value))}
                contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
              />
              <Legend />
              <Area type="monotone" dataKey="download_bytes" name={t('admin.traffic.downloadTraffic')} stroke="#10b981" fillOpacity={1} fill="url(#colorDownload)" />
              <Area type="monotone" dataKey="proxy_bytes" name={t('admin.traffic.proxyTraffic')} stroke="#f59e0b" fillOpacity={1} fill="url(#colorProxy)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 按分辨率统计 */}
      <div className="chart-section">
        <h3>{t('admin.traffic.byResolution')}</h3>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={Object.entries(traffic?.by_resolution || {}).map(([name, value]) => ({ name, value }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" tickFormatter={(v) => formatBytes(v)} />
              <Tooltip 
                formatter={(value) => formatBytes(Number(value))}
                contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
              />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 热门视频 */}
      {downloadStats?.popular_videos && downloadStats.popular_videos.length > 0 && (
        <div className="chart-section">
          <h3><TrendingUp size={20} /> {t('admin.traffic.popularVideos')}</h3>
          <div className="popular-videos-list">
            {downloadStats.popular_videos.map((video, index) => (
              <div key={index} className="popular-video-item">
                <span className="rank">#{index + 1}</span>
                <div className="video-info">
                  <span className="video-title">{video.video_title}</span>
                  <span className="video-stats">
                    {t('admin.traffic.downloads')}: {video.download_count} | {t('admin.traffic.size')}: {formatBytes(video.total_bytes)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const renderAgentGo = () => (
    <div className="agentgo-content">
      <div className="stats-row">
        <div className="stat-card">
          <h4>{t('admin.agentgo.totalCalls')}</h4>
          <span className="big-value">{agentgo?.total_calls || 0}</span>
        </div>
        <div className="stat-card success">
          <h4>{t('admin.agentgo.successfulCalls')}</h4>
          <span className="big-value">{agentgo?.successful_calls || 0}</span>
        </div>
        <div className="stat-card error">
          <h4>{t('admin.agentgo.failedCalls')}</h4>
          <span className="big-value">{agentgo?.failed_calls || 0}</span>
        </div>
        <div className="stat-card">
          <h4>{t('admin.agentgo.successRate')}</h4>
          <span className="big-value">{agentgo?.success_rate || 0}%</span>
        </div>
        <div className="stat-card">
          <h4>{t('admin.agentgo.avgDuration')}</h4>
          <span className="big-value">{agentgo?.avg_duration || 0}s</span>
        </div>
      </div>

      <div className="charts-grid">
        <div className="chart-section">
          <h3>{t('admin.agentgo.byRegion')}</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={Object.entries(agentgo?.by_region || {}).map(([name, value]) => ({ name, value }))}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label
                >
                  {Object.keys(agentgo?.by_region || {}).map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-section">
          <h3>{t('admin.agentgo.byMethod')}</h3>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={Object.entries(agentgo?.by_method || {}).map(([name, value]) => ({ name, value }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }} />
                <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {agentgo?.top_errors && agentgo.top_errors.length > 0 && (
        <div className="errors-section">
          <h3><AlertTriangle size={20} /> {t('admin.agentgo.commonErrors')}</h3>
          <ul className="errors-list">
            {agentgo.top_errors.map((err, i) => (
              <li key={i}>
                <span className="error-message">{err.error}</span>
                <span className="error-count">{err.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  const renderUsers = () => (
    <div className="users-content">
      <div className="stats-row">
        <div className="stat-card">
          <h4>{t('admin.users.totalUsers')}</h4>
          <span className="big-value">{userStats?.total_users || 0}</span>
        </div>
        <div className="stat-card success">
          <h4>{t('admin.users.premiumUsers')}</h4>
          <span className="big-value">{userStats?.premium_users || 0}</span>
        </div>
        <div className="stat-card warning">
          <h4>{t('admin.users.adminUsers')}</h4>
          <span className="big-value">{userStats?.admin_users || 0}</span>
        </div>
        <div className="stat-card info">
          <h4>{t('admin.users.recentNew')}</h4>
          <span className="big-value">{userStats?.new_users_period || 0}</span>
        </div>
      </div>

      <div className="chart-section">
        <h3><TrendingUp size={20} /> {t('admin.users.growthTrend')}</h3>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={userStats?.daily_new_users || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }} />
              <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="users-table-section">
        <h3><Users size={20} /> {t('admin.users.userList')}</h3>
        <table className="users-table">
          <thead>
            <tr>
              <th>{t('admin.users.id')}</th>
              <th>{t('admin.users.username')}</th>
              <th>{t('admin.users.email')}</th>
              <th>{t('admin.users.status')}</th>
              <th>{t('admin.users.type')}</th>
              <th>{t('admin.users.registerTime')}</th>
              <th>{t('admin.users.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.username}</td>
                <td>{user.email}</td>
                <td>
                  {user.is_active ? (
                    <span className="badge success"><CheckCircle size={12} /> {t('admin.users.active')}</span>
                  ) : (
                    <span className="badge error"><XCircle size={12} /> {t('admin.users.disabled')}</span>
                  )}
                </td>
                <td>
                  {user.is_admin && <span className="badge warning"><Shield size={12} /> {t('admin.users.admin')}</span>}
                  {user.is_premium && <span className="badge info"><Zap size={12} /> {t('admin.users.premium')}</span>}
                  {!user.is_admin && !user.is_premium && <span className="badge">{t('admin.users.normal')}</span>}
                </td>
                <td>{new Date(user.created_at).toLocaleDateString()}</td>
                <td>
                  <button 
                    className={`action-btn ${user.is_admin ? 'danger' : 'primary'}`}
                    onClick={() => handleToggleAdmin(user.id)}
                  >
                    {user.is_admin ? t('admin.users.revokeAdmin') : t('admin.users.setAdmin')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderLogs = () => (
    <div className="logs-content">
      <div className="log-tabs">
        <button 
          className={`log-tab ${logType === 'api' ? 'active' : ''}`}
          onClick={() => setLogType('api')}
        >
          <Server size={16} /> {t('admin.logs.apiLogs')}
        </button>
        <button 
          className={`log-tab ${logType === 'agentgo' ? 'active' : ''}`}
          onClick={() => setLogType('agentgo')}
        >
          <Zap size={16} /> {t('admin.logs.agentgoLogs')}
        </button>
        <button 
          className={`log-tab ${logType === 'traffic' ? 'active' : ''}`}
          onClick={() => setLogType('traffic')}
        >
          <Database size={16} /> {t('admin.logs.trafficLogs')}
        </button>
      </div>

      <table className="logs-table">
        <thead>
          <tr>
            {logType === 'api' && (
              <>
                <th>{t('admin.logs.time')}</th>
                <th>{t('admin.logs.endpoint')}</th>
                <th>{t('admin.logs.method')}</th>
                <th>{t('admin.logs.statusCode')}</th>
                <th>{t('admin.logs.responseTime')}</th>
                <th>{t('admin.logs.ip')}</th>
                <th>{t('admin.logs.country')}</th>
              </>
            )}
            {logType === 'agentgo' && (
              <>
                <th>{t('admin.logs.time')}</th>
                <th>{t('admin.logs.region')}</th>
                <th>{t('admin.logs.videoId')}</th>
                <th>{t('admin.logs.status')}</th>
                <th>{t('admin.logs.duration')}</th>
                <th>{t('admin.logs.extractionMethod')}</th>
                <th>{t('admin.logs.error')}</th>
              </>
            )}
            {logType === 'traffic' && (
              <>
                <th>{t('admin.logs.time')}</th>
                <th>{t('admin.logs.endpoint')}</th>
                <th>{t('admin.logs.videoId')}</th>
                <th>{t('admin.logs.resolution')}</th>
                <th>{t('admin.logs.traffic')}</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              {logType === 'api' && (
                <>
                  <td>{new Date(log.created_at).toLocaleString()}</td>
                  <td className="endpoint">{log.endpoint}</td>
                  <td>{log.method}</td>
                  <td>
                    <span className={`status-badge status-${Math.floor((log.status_code || 0) / 100)}xx`}>
                      {log.status_code}
                    </span>
                  </td>
                  <td>{log.response_time_ms?.toFixed(0)}ms</td>
                  <td>{log.ip_address?.substring(0, 15)}</td>
                  <td>{log.country_code || '-'}</td>
                </>
              )}
              {logType === 'agentgo' && (
                <>
                  <td>{new Date(log.created_at).toLocaleString()}</td>
                  <td>{log.region}</td>
                  <td>{log.video_id || '-'}</td>
                  <td>
                    {log.success ? (
                      <span className="badge success"><CheckCircle size={12} /></span>
                    ) : (
                      <span className="badge error"><XCircle size={12} /></span>
                    )}
                  </td>
                  <td>{log.duration_seconds?.toFixed(1)}s</td>
                  <td>{log.extraction_method || '-'}</td>
                  <td className="error-cell">{log.error_message?.substring(0, 30) || '-'}</td>
                </>
              )}
              {logType === 'traffic' && (
                <>
                  <td>{new Date(log.created_at).toLocaleString()}</td>
                  <td className="endpoint">{log.endpoint}</td>
                  <td>{log.video_id || '-'}</td>
                  <td>{log.resolution || '-'}</td>
                  <td>{formatBytes(log.total_bytes || 0)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="admin-dashboard">
      <header className="admin-header">
        <div className="header-left">
          <button onClick={onBack} className="back-btn">
            <ArrowLeft size={24} />
          </button>
          <h1><Shield size={28} /> {t('admin.title')}</h1>
        </div>
        <div className="header-right">
          <LanguageSwitcher />
          <button onClick={loadDashboardData} className="refresh-btn">
            <RefreshCw size={16} /> {t('common.refresh')}
          </button>
        </div>
      </header>

      <nav className="admin-nav">
        <button 
          className={`nav-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => handleTabChange('overview')}
        >
          <BarChart3 size={18} /> {t('admin.tabs.overview')}
        </button>
        <button 
          className={`nav-tab ${activeTab === 'traffic' ? 'active' : ''}`}
          onClick={() => handleTabChange('traffic')}
        >
          <Database size={18} /> {t('admin.tabs.traffic')}
        </button>
        <button 
          className={`nav-tab ${activeTab === 'agentgo' ? 'active' : ''}`}
          onClick={() => handleTabChange('agentgo')}
        >
          <Zap size={18} /> {t('admin.tabs.agentgo')}
        </button>
        <button 
          className={`nav-tab ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => handleTabChange('users')}
        >
          <Users size={18} /> {t('admin.tabs.users')}
        </button>
        <button 
          className={`nav-tab ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => handleTabChange('logs')}
        >
          <Server size={18} /> {t('admin.tabs.logs')}
        </button>
      </nav>

      <main className="admin-content">
        {activeTab === 'overview' && renderOverview()}
        {activeTab === 'traffic' && renderTraffic()}
        {activeTab === 'agentgo' && renderAgentGo()}
        {activeTab === 'users' && renderUsers()}
        {activeTab === 'logs' && renderLogs()}
      </main>
    </div>
  );
}

export default AdminDashboard;
