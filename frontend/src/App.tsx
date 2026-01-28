import { useState, useEffect } from 'react';
import {
  Youtube,
  Download,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Play,
  Clock,
  Link,
  Copy,
  User,
  LogOut,
  CreditCard,
  Zap,
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
import './App.css';

type AppState = 'idle' | 'extracting' | 'completed' | 'error';
type AuthState = 'login' | 'register';
type PageState = 'main' | 'payment' | 'auth';

function App() {
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

  // 页面状态
  const [pageState, setPageState] = useState<PageState>('main');

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
      setError(err.response?.data?.detail || '注册失败');
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
      setError(err.response?.data?.detail || '登录失败');
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
      setError('请输入YouTube URL');
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
        setError(response.error_message || '提取失败');
        setAppState('error');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || '提取失败';
      
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

  const handleDownload = (url: string, filename: string) => {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return '未知大小';
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
      setError('请先注册登录');
      return;
    }

    try {
      const order = await createPaymentOrder(planType);
      
      // 模拟支付成功
      const result = await completePayment(order.order_number);
      
      if (result.success) {
        alert('支付成功！您已升级为高级用户');
        await loadUserData();
        setPageState('main');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '支付失败');
    }
  };

  // 渲染登录/注册页面
  if (pageState === 'auth') {
    return (
      <div className="app auth-page">
        <div className="auth-container">
          <div className="auth-header">
            <Youtube size={48} className="auth-logo" />
            <h1>YouTube 下载器</h1>
            <p className="auth-subtitle">免费额度已用完，注册后继续使用</p>
          </div>

          <div className="auth-tabs">
            <button
              className={`auth-tab ${authState === 'login' ? 'active' : ''}`}
              onClick={() => {
                setAuthState('login');
                setError(null);
              }}
            >
              登录
            </button>
            <button
              className={`auth-tab ${authState === 'register' ? 'active' : ''}`}
              onClick={() => {
                setAuthState('register');
                setError(null);
              }}
            >
              注册
            </button>
          </div>

          <form onSubmit={authState === 'login' ? handleLogin : handleRegister} className="auth-form">
            {authState === 'register' && (
              <div className="form-group">
                <label htmlFor="username">用户名</label>
                <input
                  id="username"
                  type="text"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  placeholder="请输入用户名"
                  required
                  minLength={3}
                />
              </div>
            )}

            <div className="form-group">
              <label htmlFor="email">邮箱</label>
              <input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="请输入邮箱"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">密码</label>
              <input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="请输入密码（至少6位）"
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
              {authState === 'login' ? '登录' : '注册'}
            </button>
          </form>

          {authState === 'register' && (
            <div className="auth-info">
              <CheckCircle2 size={16} />
              <span>注册后可 <strong>无限次下载</strong></span>
            </div>
          )}

          <button onClick={() => setPageState('main')} className="back-btn" style={{marginTop: '1rem'}}>
            返回主页
          </button>
        </div>
      </div>
    );
  }

  // 渲染付费页面
  if (pageState === 'payment') {
    return (
      <div className="app">
        <header className="header">
          <div className="logo">
            <Youtube size={32} />
            <h1>YouTube 下载器</h1>
          </div>
          <div className="user-info">
            <User size={20} />
            <span>{currentUser?.username}</span>
            <button onClick={handleLogout} className="logout-btn">
              <LogOut size={16} />
            </button>
          </div>
        </header>

        <main className="main payment-page">
          <div className="payment-header">
            <CreditCard size={48} />
            <h2>升级到高级版</h2>
            <p>升级后可无限次使用</p>
          </div>

          <div className="pricing-cards">
            <div className="pricing-card">
              <div className="plan-header">
                <h3>月度会员</h3>
                <div className="price">
                  <span className="amount">¥9.99</span>
                  <span className="period">/月</span>
                </div>
              </div>
              <ul className="features">
                <li><CheckCircle2 size={16} /> 无限次下载</li>
                <li><CheckCircle2 size={16} /> 支持所有分辨率</li>
                <li><CheckCircle2 size={16} /> 高速下载</li>
                <li><CheckCircle2 size={16} /> 无广告</li>
              </ul>
              <button onClick={() => handlePayment('monthly')} className="plan-btn">
                选择月度会员
              </button>
            </div>

            <div className="pricing-card featured">
              <div className="badge">最划算</div>
              <div className="plan-header">
                <h3>年度会员</h3>
                <div className="price">
                  <span className="amount">¥99.99</span>
                  <span className="period">/年</span>
                </div>
                <div className="save-badge">节省 ¥20</div>
              </div>
              <ul className="features">
                <li><Zap size={16} /> 无限次下载</li>
                <li><Zap size={16} /> 支持所有分辨率</li>
                <li><Zap size={16} /> 高速下载</li>
                <li><Zap size={16} /> 无广告</li>
                <li><Zap size={16} /> 优先支持</li>
              </ul>
              <button onClick={() => handlePayment('yearly')} className="plan-btn featured-btn">
                选择年度会员
              </button>
            </div>
          </div>

          <button onClick={() => setPageState('main')} className="back-btn">
            返回主页
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
          <h1>YouTube 下载器</h1>
        </div>
        <div className="header-right">
          {isAuthenticated ? (
            <>
              {userQuota && currentUser?.is_premium && (
                <div className="quota-info">
                  <span className="premium-badge">
                    <Zap size={16} />
                    高级会员
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
                    免费剩余: {anonymousQuota.remaining}/3
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
                登录/注册
              </button>
            </>
          )}
          <div className="api-status">
            {isApiHealthy === null ? (
              <span className="status-checking">检查API...</span>
            ) : isApiHealthy ? (
              <span className="status-healthy">
                <CheckCircle2 size={16} /> API已连接
              </span>
            ) : (
              <span className="status-unhealthy">
                <AlertCircle size={16} /> API离线
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="main">
        {appState === 'idle' && (
          <div className="input-section">
            <h2>获取YouTube直接下载链接</h2>
            <p className="subtitle">
              {isAuthenticated ? '注册用户无限次使用' : `免费用户可使用 ${anonymousQuota?.remaining || 3} 次，注册后无限制`}
            </p>

            <form onSubmit={handleSubmit} className="url-form">
              <div className="input-group">
                <Link size={20} className="input-icon" />
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  className="url-input"
                  disabled={!isApiHealthy}
                />
              </div>

              <div className="options">
                <div className="resolution-select">
                  <label htmlFor="resolution">分辨率:</label>
                  <select
                    id="resolution"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value as VideoResolution)}
                    className="resolution-dropdown"
                  >
                    <option value="360">360p</option>
                    <option value="480">480p</option>
                    <option value="720">720p (推荐)</option>
                    <option value="1080">1080p 全高清</option>
                    <option value="1440">1440p 2K</option>
                    <option value="2160">2160p 4K</option>
                    <option value="best">最佳质量</option>
                    <option value="audio">仅音频</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="submit-btn"
                disabled={!isApiHealthy || !url.trim()}
              >
                <Download size={20} />
                获取下载链接
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
            <h2>正在提取下载链接...</h2>
            <p className="progress-text">这可能需要几秒钟</p>
          </div>
        )}

        {appState === 'completed' && result && result.video_info && result.download_urls && (
          <div className="result-section">
            <div className="success-header">
              <CheckCircle2 size={48} className="success-icon" />
              <h2>链接准备就绪！</h2>
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
                  <span>作者: {result.video_info.uploader}</span>
                )}
              </div>
            </div>

            <div className="download-links">
              <h4>推荐下载</h4>
              
              {result.download_urls.video_url && (
                <div className="link-item">
                  <div className="link-header">
                    <Play size={20} />
                    <span>视频</span>
                    {renderFormatInfo(result.download_urls.video_format, '格式')}
                  </div>
                  <div className="link-actions">
                    <button
                      onClick={() => {
                        if (result.download_urls?.video_url && result.video_info?.title) {
                          handleDownload(
                            result.download_urls.video_url,
                            `${result.video_info.title}.${result.download_urls.video_format?.ext || 'mp4'}`
                          );
                        }
                      }}
                      className="download-btn video-btn"
                    >
                      <Download size={16} />
                      下载
                    </button>
                    <button
                      onClick={() => copyToClipboard(result.download_urls!.video_url!, 'video')}
                      className="copy-btn"
                    >
                      <Copy size={16} />
                      {copiedUrl === 'video' ? '已复制!' : '复制链接'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {result.extraction_time && (
              <p className="extraction-time">
                提取用时 {result.extraction_time.toFixed(2)}秒
              </p>
            )}

            <button onClick={handleReset} className="reset-btn">
              下载另一个视频
            </button>
          </div>
        )}

        {appState === 'error' && (
          <div className="error-section">
            <AlertCircle size={48} className="error-icon" />
            <h2>提取失败</h2>
            <p className="error-detail">{error}</p>
            <button onClick={handleReset} className="reset-btn">
              重试
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>YouTube 下载器 &copy; 2024 | 免费3次，注册无限制</p>
      </footer>
    </div>
  );
}

export default App;
