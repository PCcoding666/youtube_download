import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Youtube,
  Download,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Info,
  Play,
  Clock,
  Link,
  Copy,
  User,
  LogOut,
  CreditCard,
  Shield,
  Key,
  Coins,
} from 'lucide-react';
import {
  extractDirectURLs,
  healthCheck,
  register,
  login,
  logout,
  getCurrentUser,
  getUserQuota,
  getCreditBalance,
  getAuthToken,
  checkAnonymousQuota,
} from './api';
import type { ExtractURLResponse, VideoResolution, VideoFormatInfo, UserInfo, RegisterRequest, LoginRequest } from './api';
import AdminDashboard from './components/admin/AdminDashboard';
import PricingPage from './components/pricing/PricingPage';
import ApiKeyManager from './components/apikeys/ApiKeyManager';
import LanguageSwitcher from './components/LanguageSwitcher';
import './App.css';

type AppState = 'idle' | 'extracting' | 'completed' | 'error';
type AuthState = 'login' | 'register';

// Progress stages for download (user-friendly names, no internal details)
interface ProgressStage {
  label: string;         // i18n key
  percent: number;       // target percentage
  duration: number;      // estimated seconds for this stage
}

const PROGRESS_STAGES: ProgressStage[] = [
  { label: 'progress.connecting',  percent: 10,  duration: 2 },
  { label: 'progress.analyzing',   percent: 25,  duration: 5 },
  { label: 'progress.preparing',   percent: 40,  duration: 8 },
  { label: 'progress.downloading', percent: 70,  duration: 15 },
  { label: 'progress.processing',  percent: 85,  duration: 10 },
  { label: 'progress.finalizing',  percent: 95,  duration: 5 },
];
type PageState = 'main' | 'payment' | 'auth' | 'admin' | 'pricing' | 'apikeys';

const VALID_PAGES: PageState[] = ['main', 'payment', 'auth', 'admin', 'pricing', 'apikeys'];

// 从 URL 参数获取初始页面状态
function getInitialPageState(): PageState {
  const params = new URLSearchParams(window.location.search);
  const page = params.get('page');
  if (page && VALID_PAGES.includes(page as PageState)) {
    return page as PageState;
  }
  return 'main';
}

// 更新 URL 参数
function updatePageUrl(page: PageState) {
  const url = new URL(window.location.href);
  if (page === 'main') {
    url.searchParams.delete('page');
  } else {
    url.searchParams.set('page', page);
  }
  window.history.replaceState({}, '', url.toString());
}

function App() {
  const { t } = useTranslation();
  const [url, setUrl] = useState('');
  const [resolution, setResolution] = useState<VideoResolution>('720');
  const [appState, setAppState] = useState<AppState>('idle');
  const [result, setResult] = useState<ExtractURLResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isApiHealthy, setIsApiHealthy] = useState<boolean | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  // 认证状态
  const [authState, setAuthState] = useState<AuthState>('login');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
  const [_userQuota, setUserQuota] = useState<any>(null);
  const [creditBalance, setCreditBalance] = useState<number>(0);

  // 匿名配额
  const [anonymousQuota, setAnonymousQuota] = useState<any>(null);

  // 进度条状态
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [estimatedTotal, setEstimatedTotal] = useState(45); // 预估总时间（秒）

  // 页面状态 - 从 URL 读取初始值
  const [pageState, setPageStateInternal] = useState<PageState>(getInitialPageState);

  // 切换页面并更新 URL
  const setPageState = (page: PageState) => {
    setPageStateInternal(page);
    updatePageUrl(page);
  };

  // 表单状态
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
  });

  useEffect(() => {
    const checkHealth = async () => {
      const healthy = await healthCheck();
      setIsApiHealthy(healthy);
    };
    checkHealth();

    // 检查是否已登录
    const token = getAuthToken();
    if (token) {
      loadUserData();
    } else {
      // 加载匿名配额
      loadAnonymousQuota();
    }
  }, []);

  // 进度条模拟：根据阶段自动推进
  useEffect(() => {
    if (appState !== 'extracting') return;

    const totalEstimated = PROGRESS_STAGES.reduce((sum, s) => sum + s.duration, 0);
    setEstimatedTotal(totalEstimated);

    let stageIdx = 0;
    let stageStart = Date.now();
    let elapsed = 0;

    const timer = setInterval(() => {
      elapsed += 0.3;
      setElapsedTime(Math.floor(elapsed));

      if (stageIdx >= PROGRESS_STAGES.length) {
        // 已到最后阶段，缓慢逼近 98%
        setProgress((prev) => Math.min(prev + 0.1, 98));
        return;
      }

      const stage = PROGRESS_STAGES[stageIdx];
      const stageElapsed = (Date.now() - stageStart) / 1000;
      const stageProgress = Math.min(stageElapsed / stage.duration, 1);

      const prevPercent = stageIdx > 0 ? PROGRESS_STAGES[stageIdx - 1].percent : 0;
      const currentPercent = prevPercent + (stage.percent - prevPercent) * stageProgress;

      setProgress(Math.min(currentPercent, 98));
      setProgressStage(stageIdx);

      if (stageElapsed >= stage.duration) {
        stageIdx++;
        stageStart = Date.now();
        if (stageIdx < PROGRESS_STAGES.length) {
          setProgressStage(stageIdx);
        }
      }
    }, 300);

    return () => clearInterval(timer);
  }, [appState]);

  // 完成/失败时，进度跳到 100% 或重置
  useEffect(() => {
    if (appState === 'completed') {
      setProgress(100);
    } else if (appState === 'idle' || appState === 'error') {
      setProgress(0);
      setProgressStage(0);
      setElapsedTime(0);
    }
  }, [appState]);

  const loadUserData = async () => {
    try {
      const user = await getCurrentUser();
      setCurrentUser(user);
      setIsAuthenticated(true);

      const quota = await getUserQuota();
      setUserQuota(quota);

      // 加载 credit 余额
      try {
        const balance = await getCreditBalance();
        setCreditBalance(balance.credit_balance);
      } catch {
        // 如果 credit 余额 API 还没有数据，使用 user 返回的
        setCreditBalance((user as any)?.credit_balance || 0);
      }
    } catch (err) {
      console.error('Failed to load user data:', err);
      setIsAuthenticated(false);
      // 登录失败，加载匿名配额
      loadAnonymousQuota();
    }
  };

  const loadAnonymousQuota = async () => {
    try {
      const quota = await checkAnonymousQuota();
      setAnonymousQuota(quota);
    } catch (err) {
      console.error('Failed to load anonymous quota:', err);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    // 前端验证
    if (formData.username.length < 3) {
      setError(t('auth.usernameTooShort'));
      return;
    }
    if (formData.password.length < 6) {
      setError(t('auth.passwordTooShort'));
      return;
    }
    
    try {
      const request: RegisterRequest = {
        username: formData.username,
        email: formData.email,
        password: formData.password,
      };
      const response = await register(request);
      if (response.success) {
        await loadUserData();
        setPageState('main');
      } else {
        setError(response.message);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t('auth.registerFailed'));
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const request: LoginRequest = {
        email: formData.email,
        password: formData.password,
      };
      const response = await login(request);
      if (response.success) {
        await loadUserData();
        setPageState('main');
      } else {
        setError(response.message);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t('auth.loginFailed'));
    }
  };

  const handleLogout = async () => {
    await logout();
    setIsAuthenticated(false);
    setCurrentUser(null);
    setUserQuota(null);
    loadAnonymousQuota();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!url.trim()) {
      setError(t('main.enterYoutubeUrl'));
      return;
    }

    setError(null);
    setResult(null);
    setAppState('extracting');

    try {
      const response = await extractDirectURLs({
        youtube_url: url,
        resolution: resolution,
      });

      if (response.success) {
        setResult(response);
        setAppState('completed');
        // 刷新配额信息
        if (isAuthenticated) {
          await loadUserData();
        } else {
          await loadAnonymousQuota();
        }
      } else {
        setError(response.error_message || t('main.extractionFailed'));
        setAppState('error');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || t('main.extractionFailed');
      
      // 检查是否是 credit 不足的错误
      if (err.response?.status === 402) {
        setPageState(isAuthenticated ? 'pricing' : 'auth');
        setError(errorMessage);
      } else {
        setError(errorMessage);
      }
      setAppState('error');
    }
  };

  const handleReset = () => {
    setUrl('');
    setAppState('idle');
    setResult(null);
    setError(null);
  };

  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedUrl(label);
      setTimeout(() => setCopiedUrl(null), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleDownload = (url: string, filename: string, resolution?: string) => {
    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    let downloadUrl: string;

    if (url.includes('googlevideo.com')) {
      // YouTube CDN 链接 → 使用后端代理下载以绕过防盗链
      downloadUrl = `${API_BASE_URL}/api/v1/proxy-download?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(filename)}&resolution=${encodeURIComponent(resolution || 'unknown')}`;
    } else if (url.includes('.aliyuncs.com/')) {
      // OSS 链接 → 通过后端获取签名URL（处理私有bucket + URL过期场景）
      // 从 URL 中提取 object_key（域名后面的路径部分，去掉签名参数）
      try {
        const ossUrl = new URL(url);
        const objectKey = decodeURIComponent(ossUrl.pathname.slice(1)); // 去掉前导 /
        downloadUrl = `${API_BASE_URL}/api/v1/oss-download?object_key=${encodeURIComponent(objectKey)}&filename=${encodeURIComponent(filename)}`;
      } catch {
        // URL 解析失败，直接使用原始 URL
        downloadUrl = url;
      }
    } else {
      // 其他链接，直接下载
      downloadUrl = url;
    }

    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return t('common.unknown') || 'Unknown size';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  const renderFormatInfo = (format: VideoFormatInfo | null, label: string) => {
    if (!format) return null;
    return (
      <div className="format-info">
        <span className="format-label">{label}:</span>
        <span className="format-details">
          {format.height ? `${format.height}p` : format.resolution || 'N/A'}
          {format.ext && ` • ${format.ext.toUpperCase()}`}
          {format.filesize && ` • ${formatFileSize(format.filesize)}`}
        </span>
      </div>
    );
  };

  // 渲染登录/注册页面
  if (pageState === 'auth') {
    return (
      <div className="app auth-page">
        <div className="auth-container">
          <div className="auth-header">
            <Youtube size={48} className="auth-logo" />
            <h1>{t('common.appName')}</h1>
            <p className="auth-subtitle">{t('auth.subtitle')}</p>
          </div>

          <div className="auth-lang-switcher">
            <LanguageSwitcher />
          </div>

          <div className="auth-tabs">
            <button
              className={`auth-tab ${authState === 'login' ? 'active' : ''}`}
              onClick={() => {
                setAuthState('login');
                setError(null);
              }}
            >
              {t('auth.login')}
            </button>
            <button
              className={`auth-tab ${authState === 'register' ? 'active' : ''}`}
              onClick={() => {
                setAuthState('register');
                setError(null);
              }}
            >
              {t('auth.register')}
            </button>
          </div>

          <form onSubmit={authState === 'login' ? handleLogin : handleRegister} className="auth-form">
            {authState === 'register' && (
              <div className="form-group">
                <label htmlFor="username">{t('auth.username')}</label>
                <input
                  id="username"
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  placeholder={t('auth.enterUsername')}
                  required
                  minLength={3}
                />
              </div>
            )}

            <div className="form-group">
              <label htmlFor="email">{t('auth.email')}</label>
              <input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder={t('auth.enterEmail')}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">{t('auth.password')}</label>
              <input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder={t('auth.enterPassword')}
                required
                minLength={6}
              />
            </div>

            {error && (
              <div className="auth-error">
                <AlertCircle size={16} />
                {error}
              </div>
            )}

            <button type="submit" className="auth-submit">
              {authState === 'login' ? t('auth.login') : t('auth.register')}
            </button>
          </form>

          {authState === 'register' && !error && (
            <div className="auth-tip">
              <Info size={16} />
              <span>{t('auth.registerBenefit')}</span>
            </div>
          )}

          <button onClick={() => setPageState('main')} className="back-btn" style={{marginTop: '1rem'}}>
            {t('common.backToHome')}
          </button>
        </div>
      </div>
    );
  }

  // 渲染管理员页面
  if (pageState === 'admin' && currentUser?.is_admin) {
    return <AdminDashboard onBack={() => setPageState('main')} />;
  }

  // 渲染定价/充值页面
  if (pageState === 'pricing' || pageState === 'payment') {
    return (
      <PricingPage
        onBack={() => setPageState('main')}
        onSelectPlan={() => {
          if (!isAuthenticated) {
            setPageState('auth');
          }
        }}
        isAuthenticated={isAuthenticated}
        currentPlan={undefined}
      />
    );
  }

  // 渲染 API Key 管理页面
  if (pageState === 'apikeys' && isAuthenticated) {
    return (
      <ApiKeyManager
        onBack={() => setPageState('main')}
        creditBalance={creditBalance}
      />
    );
  }

  // 渲染主页面
  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <Youtube size={32} />
          <h1>{t('common.appName')}</h1>
        </div>
        <div className="header-right">
          <LanguageSwitcher />
          <button
            onClick={() => setPageState('pricing')}
            className="nav-pricing-btn"
          >
            <CreditCard size={16} />
            {t('header.pricing')}
          </button>
          {isAuthenticated ? (
            <>
              {currentUser?.is_admin && (
                <button
                  onClick={() => setPageState('admin')}
                  className="admin-btn"
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: 'rgba(234, 179, 8, 0.2)',
                    color: '#facc15',
                    border: '1px solid rgba(234, 179, 8, 0.3)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    fontSize: '0.875rem',
                  }}
                >
                  <Shield size={16} />
                  {t('header.adminPanel')}
                </button>
              )}
              {/* Credit Balance */}
              <div className="quota-info" style={{ cursor: 'pointer' }} onClick={() => setPageState('pricing')}>
                <span className="premium-badge" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <Coins size={16} style={{ color: '#fbbf24' }} />
                  {creditBalance} Credits
                </span>
              </div>
              {/* API Key Button */}
              <button
                onClick={() => setPageState('apikeys')}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                  color: '#93c5fd',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontSize: '0.875rem',
                }}
              >
                <Key size={16} />
                API Keys
              </button>
              <div className="user-info">
                <User size={20} />
                <span>{currentUser?.username}</span>
                <button onClick={handleLogout} className="logout-btn">
                  <LogOut size={16} />
                </button>
              </div>
            </>
          ) : (
            <>
              {anonymousQuota && (
                <div className="quota-info">
                  <span className="quota-badge">
                    {t('header.freeRemaining', { count: anonymousQuota.remaining })}
                  </span>
                </div>
              )}
              <button 
                onClick={() => setPageState('auth')} 
                className="login-btn"
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: 'var(--primary-color)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem'
                }}
              >
                <User size={16} />
                {t('auth.loginRegister')}
              </button>
            </>
          )}
          <div className="api-status">
            {isApiHealthy === null ? (
              <span className="status-checking">{t('header.apiChecking')}</span>
            ) : isApiHealthy ? (
              <span className="status-healthy">
                <CheckCircle2 size={16} /> {t('header.apiConnected')}
              </span>
            ) : (
              <span className="status-unhealthy">
                <AlertCircle size={16} /> {t('header.apiOffline')}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="main">
        {appState === 'idle' && (
          <div className="input-section">
            <h2>{t('main.title')}</h2>
            <p className="subtitle">
              {isAuthenticated 
                ? t('main.subtitleCredit', { credits: creditBalance }).replace('{{credits}}', String(creditBalance)) || `You have ${creditBalance} credits. Each download costs 1 credit.`
                : t('main.subtitleFree', { remaining: anonymousQuota?.remaining || 3 })}
            </p>

            <form onSubmit={handleSubmit} className="url-form">
              <div className="input-group">
                <Link size={20} className="input-icon" />
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={t('main.placeholder')}
                  className="url-input"
                  disabled={!isApiHealthy}
                />
              </div>

              <div className="options">
                <div className="resolution-select">
                  <label htmlFor="resolution">{t('main.resolution')}</label>
                  <select
                    id="resolution"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value as VideoResolution)}
                    className="resolution-dropdown"
                  >
                    <option value="360">{t('main.resolution360')}</option>
                    <option value="480">{t('main.resolution480')}</option>
                    <option value="720">{t('main.resolution720')}</option>
                    <option value="1080">{t('main.resolution1080')}</option>
                    <option value="1440">{t('main.resolution1440')}</option>
                    <option value="2160">{t('main.resolution2160')}</option>
                    <option value="best">{t('main.resolutionBest')}</option>
                    <option value="audio">{t('main.resolutionAudio')}</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="submit-btn"
                disabled={!isApiHealthy || !url.trim()}
              >
                <Download size={20} />
                {t('main.getDownloadLink')}
              </button>
            </form>

            {error && (
              <div className="error-message">
                <AlertCircle size={20} />
                {error}
              </div>
            )}
          </div>
        )}

        {appState === 'extracting' && (
          <div className="processing-section">
            <div className="processing-icon">
              <Loader2 size={48} className="spinning" />
            </div>
            <h2>{t(PROGRESS_STAGES[progressStage]?.label || 'progress.connecting')}</h2>
            
            {/* 进度条 */}
            <div className="progress-bar-container">
              <div className="progress-bar-track">
                <div 
                  className="progress-bar-fill" 
                  style={{ width: `${Math.round(progress)}%` }}
                />
              </div>
              <div className="progress-bar-info">
                <span className="progress-percent">{Math.round(progress)}%</span>
                <span className="progress-time">
                  {elapsedTime > 0 && (
                    <>
                      {t('progress.elapsed', { time: elapsedTime })}
                      {progress > 10 && progress < 95 && (
                        <> · {t('progress.remaining', { 
                          time: Math.max(1, Math.round((estimatedTotal - elapsedTime) * (1 - progress / 100) / (progress / 100)))
                        })}</>
                      )}
                    </>
                  )}
                </span>
              </div>
            </div>

            {/* 阶段指示器 */}
            <div className="progress-stages">
              {PROGRESS_STAGES.map((stage, idx) => (
                <div 
                  key={idx} 
                  className={`progress-stage-dot ${
                    idx < progressStage ? 'completed' : 
                    idx === progressStage ? 'active' : 'pending'
                  }`}
                >
                  <div className="dot" />
                  <span>{t(stage.label)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {appState === 'completed' && result && result.video_info && result.download_urls && (
          <div className="result-section">
            <div className="success-header">
              <CheckCircle2 size={48} className="success-icon" />
              <h2>{t('main.linksReady')}</h2>
            </div>

            <div className="video-info">
              {result.video_info.thumbnail && (
                <img 
                  src={result.video_info.thumbnail} 
                  alt={result.video_info.title}
                  className="video-thumbnail"
                />
              )}
              <h3>{result.video_info.title}</h3>
              <div className="video-meta">
                <span>
                  <Clock size={16} />
                  {formatDuration(result.video_info.duration)}
                </span>
                {result.video_info.uploader && (
                  <span>{t('main.author')}: {result.video_info.uploader}</span>
                )}
              </div>
            </div>

            <div className="download-links">
              <h4>{t('main.recommended')}</h4>
              
              {result.download_urls.video_url && (
                <div className="link-item">
                  <div className="link-header">
                    <Play size={20} />
                    <span>{t('main.video')}</span>
                    {renderFormatInfo(result.download_urls.video_format, t('main.format'))}
                  </div>
                  <div className="link-actions">
                    <button
                      onClick={() => {
                        if (result.download_urls?.video_url && result.video_info?.title) {
                          handleDownload(
                            result.download_urls.video_url,
                            `${result.video_info.title}.${result.download_urls.video_format?.ext || 'mp4'}`,
                            result.download_urls.video_format?.resolution || resolution
                          );
                        }
                      }}
                      className="download-btn video-btn"
                    >
                      <Download size={16} />
                      {t('common.download')}
                    </button>
                    <button
                      onClick={() => copyToClipboard(result.download_urls!.video_url!, 'video')}
                      className="copy-btn"
                    >
                      <Copy size={16} />
                      {copiedUrl === 'video' ? t('common.copied') : t('main.copyLink')}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {result.extraction_time && (
              <p className="extraction-time">
                {t('main.extractionTime', { time: result.extraction_time.toFixed(2) })}
              </p>
            )}

            <button onClick={handleReset} className="reset-btn">
              {t('main.downloadAnother')}
            </button>
          </div>
        )}

        {appState === 'error' && (
          <div className="error-section">
            <AlertCircle size={48} className="error-icon" />
            <h2>{t('main.extractionFailed')}</h2>
            <p className="error-detail">{error}</p>
            <button onClick={handleReset} className="reset-btn">
              {t('common.retry')}
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>{t('footer.copyright')}</p>
      </footer>
    </div>
  );
}

export default App;
