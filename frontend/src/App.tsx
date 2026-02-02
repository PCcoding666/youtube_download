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
  Zap,
  Shield,
} from 'lucide-react';
import {
  extractDirectURLs,
  healthCheck,
  register,
  login,
  logout,
  getCurrentUser,
  getUserQuota,
  createPaymentOrder,
  completePayment,
  getAuthToken,
  checkAnonymousQuota,
} from './api';
import type { ExtractURLResponse, VideoResolution, VideoFormatInfo, UserInfo, RegisterRequest, LoginRequest } from './api';
import AdminDashboard from './components/admin/AdminDashboard';
import PricingPage from './components/pricing/PricingPage';
import LanguageSwitcher from './components/LanguageSwitcher';
import './App.css';

type AppState = 'idle' | 'extracting' | 'completed' | 'error';
type AuthState = 'login' | 'register';
type PageState = 'main' | 'payment' | 'auth' | 'admin' | 'pricing';

const VALID_PAGES: PageState[] = ['main', 'payment', 'auth', 'admin', 'pricing'];

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
  const [userQuota, setUserQuota] = useState<any>(null);

  // 匿名配额
  const [anonymousQuota, setAnonymousQuota] = useState<any>(null);

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

  const loadUserData = async () => {
    try {
      const user = await getCurrentUser();
      setCurrentUser(user);
      setIsAuthenticated(true);

      const quota = await getUserQuota();
      setUserQuota(quota);
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
      
      // 检查是否是配额用完的错误
      if (err.response?.status === 402) {
        setPageState(isAuthenticated ? 'payment' : 'auth');
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
    // 检查是否是 YouTube CDN 链接（googlevideo.com）
    // 如果是，使用后端代理下载以绕过防盗链
    if (url.includes('googlevideo.com')) {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const proxyUrl = `${API_BASE_URL}/api/v1/proxy-download?url=${encodeURIComponent(url)}&filename=${encodeURIComponent(filename)}&resolution=${encodeURIComponent(resolution || 'unknown')}`;
      const link = document.createElement('a');
      link.href = proxyUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      // 非 YouTube CDN 链接（如 OSS 链接），直接下载
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
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

  const handlePayment = async (planType: 'monthly' | 'yearly') => {
    if (!isAuthenticated) {
      setError(t('payment.pleaseLogin'));
      return;
    }

    try {
      const order = await createPaymentOrder(planType);
      
      // 模拟支付成功
      const result = await completePayment(order.order_number);
      
      if (result.success) {
        alert(t('payment.paymentSuccess'));
        await loadUserData();
        setPageState('main');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t('payment.paymentFailed'));
    }
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

  // 渲染定价页面
  if (pageState === 'pricing') {
    return (
      <PricingPage
        onBack={() => setPageState('main')}
        onSelectPlan={(plan) => {
          if (!isAuthenticated) {
            setPageState('auth');
          } else {
            handlePayment(plan as 'monthly' | 'yearly');
          }
        }}
        isAuthenticated={isAuthenticated}
        currentPlan={currentUser?.is_premium ? 'pro' : 'free'}
      />
    );
  }

  // 渲染付费页面
  if (pageState === 'payment') {
    return (
      <div className="app">
        <header className="header">
          <div className="logo">
            <Youtube size={32} />
            <h1>{t('common.appName')}</h1>
          </div>
          <div className="header-right">
            <LanguageSwitcher />
            <div className="user-info">
              <User size={20} />
              <span>{currentUser?.username}</span>
              <button onClick={handleLogout} className="logout-btn">
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </header>

        <main className="main payment-page">
          <div className="payment-header">
            <CreditCard size={48} />
            <h2>{t('payment.upgradeTitle')}</h2>
            <p>{t('payment.upgradeDesc')}</p>
          </div>

          <div className="pricing-cards">
            <div className="pricing-card">
              <div className="plan-header">
                <h3>{t('payment.monthlyPlan')}</h3>
                <div className="price">
                  <span className="amount">¥9.99</span>
                  <span className="period">{t('payment.perMonth')}</span>
                </div>
              </div>
              <ul className="features">
                <li><CheckCircle2 size={16} /> {t('payment.features.unlimited')}</li>
                <li><CheckCircle2 size={16} /> {t('payment.features.allResolutions')}</li>
                <li><CheckCircle2 size={16} /> {t('payment.features.highSpeed')}</li>
                <li><CheckCircle2 size={16} /> {t('payment.features.noAds')}</li>
              </ul>
              <button onClick={() => handlePayment('monthly')} className="plan-btn">
                {t('payment.selectMonthly')}
              </button>
            </div>

            <div className="pricing-card featured">
              <div className="badge">{t('payment.bestValue')}</div>
              <div className="plan-header">
                <h3>{t('payment.yearlyPlan')}</h3>
                <div className="price">
                  <span className="amount">¥99.99</span>
                  <span className="period">{t('payment.perYear')}</span>
                </div>
                <div className="save-badge">{t('payment.save')}</div>
              </div>
              <ul className="features">
                <li><Zap size={16} /> {t('payment.features.unlimited')}</li>
                <li><Zap size={16} /> {t('payment.features.allResolutions')}</li>
                <li><Zap size={16} /> {t('payment.features.highSpeed')}</li>
                <li><Zap size={16} /> {t('payment.features.noAds')}</li>
                <li><Zap size={16} /> {t('payment.features.prioritySupport')}</li>
              </ul>
              <button onClick={() => handlePayment('yearly')} className="plan-btn featured-btn">
                {t('payment.selectYearly')}
              </button>
            </div>
          </div>

          <button onClick={() => setPageState('main')} className="back-btn">
            {t('common.backToHome')}
          </button>
        </main>
      </div>
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
              {userQuota && currentUser?.is_premium && (
                <div className="quota-info">
                  <span className="premium-badge">
                    <Zap size={16} />
                    {t('header.premiumMember')}
                  </span>
                </div>
              )}
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
                ? (currentUser?.is_premium ? t('main.subtitleAuthenticated') : t('main.subtitlePremium'))
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
            <h2>{t('main.extracting')}</h2>
            <p className="progress-text">{t('main.extractingDesc')}</p>
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
