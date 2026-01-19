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
  Volume2,
  Copy,
} from 'lucide-react';
import {
  extractDirectURLs,
  healthCheck,
} from './api';
import type { ExtractURLResponse, VideoResolution, VideoFormatInfo } from './api';
import './App.css';

type AppState = 'idle' | 'extracting' | 'completed' | 'error';

function App() {
  const [url, setUrl] = useState('');
  const [resolution, setResolution] = useState<VideoResolution>('720');
  const [appState, setAppState] = useState<AppState>('idle');
  const [result, setResult] = useState<ExtractURLResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isApiHealthy, setIsApiHealthy] = useState<boolean | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      const healthy = await healthCheck();
      setIsApiHealthy(healthy);
    };
    checkHealth();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!url.trim()) {
      setError('Please enter a YouTube URL');
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
      } else {
        setError(response.error_message || 'Failed to extract URLs');
        setAppState('error');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to extract URLs';
      setError(errorMessage);
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
    // Direct download - open in new tab
    // The browser will handle the download
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return 'Unknown size';
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
          {format.vcodec && format.vcodec !== 'none' && ` • ${format.vcodec}`}
          {format.acodec && format.acodec !== 'none' && ` • ${format.acodec}`}
        </span>
      </div>
    );
  };

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <Youtube size={32} />
          <h1>YouTube Direct Link</h1>
        </div>
        <div className="api-status">
          {isApiHealthy === null ? (
            <span className="status-checking">Checking API...</span>
          ) : isApiHealthy ? (
            <span className="status-healthy">
              <CheckCircle2 size={16} /> API Connected
            </span>
          ) : (
            <span className="status-unhealthy">
              <AlertCircle size={16} /> API Offline
            </span>
          )}
        </div>
      </header>

      <main className="main">
        {appState === 'idle' && (
          <div className="input-section">
            <h2>Get YouTube Direct Download Links</h2>
            <p className="subtitle">
              Enter a YouTube URL to get direct download links. No server download - links go directly to YouTube.
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
                  <label htmlFor="resolution">Resolution:</label>
                  <select
                    id="resolution"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value as VideoResolution)}
                    className="resolution-dropdown"
                  >
                    <option value="360">360p</option>
                    <option value="480">480p</option>
                    <option value="720">720p (Recommended)</option>
                    <option value="1080">1080p Full HD</option>
                    <option value="1440">1440p 2K</option>
                    <option value="2160">2160p 4K</option>
                    <option value="best">Best Available</option>
                    <option value="audio">Audio Only</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="submit-btn"
                disabled={!isApiHealthy || !url.trim()}
              >
                <Download size={20} />
                Get Download Links
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
            <h2>Extracting download links...</h2>
            <p className="progress-text">This may take a few seconds</p>
          </div>
        )}

        {appState === 'completed' && result && result.video_info && result.download_urls && (
          <div className="result-section">
            <div className="success-header">
              <CheckCircle2 size={48} className="success-icon" />
              <h2>Links Ready!</h2>
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
                  <span>by {result.video_info.uploader}</span>
                )}
                <span>{result.video_info.format_count} formats available</span>
              </div>
            </div>

            <div className="download-links">
              <h4>Recommended Downloads</h4>
              <div className="download-notice" style={{
                padding: '10px',
                marginBottom: '15px',
                backgroundColor: '#fff3cd',
                borderLeft: '3px solid #ffc107',
                borderRadius: '4px',
                fontSize: '14px',
                color: '#856404'
              }}>
                ⚠️ <strong>Note:</strong> Direct download links are IP-restricted by YouTube. 
                If you get a 403 error, the link can only be accessed from the server that extracted it.
              </div>
              
              {result.download_urls.video_url && (
                <div className="link-item">
                  <div className="link-header">
                    <Play size={20} />
                    <span>Video</span>
                    {renderFormatInfo(result.download_urls.video_format, 'Format')}
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
                      Download
                    </button>
                    <button
                      onClick={() => copyToClipboard(result.download_urls!.video_url!, 'video')}
                      className="copy-btn"
                    >
                      <Copy size={16} />
                      {copiedUrl === 'video' ? 'Copied!' : 'Copy URL'}
                    </button>
                  </div>
                </div>
              )}

              {result.download_urls.audio_url && (
                <div className="link-item">
                  <div className="link-header">
                    <Volume2 size={20} />
                    <span>Audio</span>
                    {renderFormatInfo(result.download_urls.audio_format, 'Format')}
                  </div>
                  <div className="link-actions">
                    <button
                      onClick={() => {
                        if (result.download_urls?.audio_url && result.video_info?.title) {
                          handleDownload(
                            result.download_urls.audio_url,
                            `${result.video_info.title}.${result.download_urls.audio_format?.ext || 'webm'}`
                          );
                        }
                      }}
                      className="download-btn audio-btn"
                    >
                      <Download size={16} />
                      Download
                    </button>
                    <button
                      onClick={() => copyToClipboard(result.download_urls!.audio_url!, 'audio')}
                      className="copy-btn"
                    >
                      <Copy size={16} />
                      {copiedUrl === 'audio' ? 'Copied!' : 'Copy URL'}
                    </button>
                  </div>
                </div>
              )}

              {result.download_urls.needs_merge && (
                <div className="merge-notice">
                  <AlertCircle size={16} />
                  Note: Video and audio are separate. Use a tool like FFmpeg to merge them.
                </div>
              )}
            </div>

            {/* All Available Formats Section */}
            {result.all_formats && result.all_formats.length > 0 && (
              <div className="all-formats-section" style={{ marginTop: '30px' }}>
                <h4 style={{ marginBottom: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Link size={20} />
                  All Available Formats ({result.all_formats.length})
                </h4>
                
                {/* Video Formats */}
                <div className="format-group" style={{ marginBottom: '20px' }}>
                  <h5 style={{ 
                    color: '#4CAF50', 
                    marginBottom: '10px',
                    fontSize: '14px',
                    fontWeight: '600'
                  }}>
                    🎬 Video Formats
                  </h5>
                  <div className="formats-table" style={{
                    backgroundColor: '#f8f9fa',
                    borderRadius: '8px',
                    overflow: 'hidden'
                  }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#e9ecef' }}>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Quality</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Format</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Codec</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Size</th>
                          <th style={{ padding: '10px', textAlign: 'center' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.all_formats
                          .filter(f => f.is_video && f.url)
                          .sort((a, b) => (b.height || 0) - (a.height || 0))
                          .map((format, idx) => (
                            <tr key={`video-${idx}`} style={{ 
                              borderBottom: '1px solid #dee2e6',
                              backgroundColor: format.has_both ? '#e8f5e9' : 'transparent'
                            }}>
                              <td style={{ padding: '10px' }}>
                                <strong>{format.height ? `${format.height}p` : format.resolution || 'N/A'}</strong>
                                {format.fps && <span style={{ color: '#666', marginLeft: '4px' }}>@{Math.round(format.fps)}fps</span>}
                                {format.has_both && <span style={{ 
                                  marginLeft: '8px', 
                                  backgroundColor: '#4CAF50', 
                                  color: 'white', 
                                  padding: '2px 6px', 
                                  borderRadius: '4px',
                                  fontSize: '11px'
                                }}>+Audio</span>}
                              </td>
                              <td style={{ padding: '10px' }}>
                                <span style={{ 
                                  backgroundColor: format.ext === 'mp4' ? '#2196F3' : '#9C27B0',
                                  color: 'white',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  fontSize: '12px'
                                }}>
                                  {format.ext?.toUpperCase() || 'N/A'}
                                </span>
                              </td>
                              <td style={{ padding: '10px', color: '#666', fontSize: '12px' }}>
                                {format.vcodec && format.vcodec !== 'none' ? format.vcodec.split('.')[0] : '-'}
                              </td>
                              <td style={{ padding: '10px', color: '#666' }}>
                                {formatFileSize(format.filesize)}
                              </td>
                              <td style={{ padding: '10px', textAlign: 'center' }}>
                                <button
                                  onClick={() => copyToClipboard(format.url, `format-${format.format_id}`)}
                                  style={{
                                    padding: '4px 12px',
                                    fontSize: '12px',
                                    backgroundColor: copiedUrl === `format-${format.format_id}` ? '#4CAF50' : '#6c757d',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  {copiedUrl === `format-${format.format_id}` ? '✓ Copied' : 'Copy URL'}
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Audio Formats */}
                <div className="format-group">
                  <h5 style={{ 
                    color: '#FF9800', 
                    marginBottom: '10px',
                    fontSize: '14px',
                    fontWeight: '600'
                  }}>
                    🎵 Audio Formats
                  </h5>
                  <div className="formats-table" style={{
                    backgroundColor: '#f8f9fa',
                    borderRadius: '8px',
                    overflow: 'hidden'
                  }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ backgroundColor: '#e9ecef' }}>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Quality</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Format</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Codec</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Bitrate</th>
                          <th style={{ padding: '10px', textAlign: 'left' }}>Size</th>
                          <th style={{ padding: '10px', textAlign: 'center' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.all_formats
                          .filter(f => f.is_audio_only && f.url)
                          .sort((a, b) => (b.tbr || 0) - (a.tbr || 0))
                          .map((format, idx) => (
                            <tr key={`audio-${idx}`} style={{ borderBottom: '1px solid #dee2e6' }}>
                              <td style={{ padding: '10px' }}>
                                <strong>{format.format_note || 'Audio'}</strong>
                              </td>
                              <td style={{ padding: '10px' }}>
                                <span style={{ 
                                  backgroundColor: format.ext === 'm4a' ? '#FF9800' : '#607D8B',
                                  color: 'white',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  fontSize: '12px'
                                }}>
                                  {format.ext?.toUpperCase() || 'N/A'}
                                </span>
                              </td>
                              <td style={{ padding: '10px', color: '#666', fontSize: '12px' }}>
                                {format.acodec && format.acodec !== 'none' ? format.acodec.split('.')[0] : '-'}
                              </td>
                              <td style={{ padding: '10px', color: '#666' }}>
                                {format.tbr ? `${Math.round(format.tbr)} kbps` : '-'}
                              </td>
                              <td style={{ padding: '10px', color: '#666' }}>
                                {formatFileSize(format.filesize)}
                              </td>
                              <td style={{ padding: '10px', textAlign: 'center' }}>
                                <button
                                  onClick={() => copyToClipboard(format.url, `format-${format.format_id}`)}
                                  style={{
                                    padding: '4px 12px',
                                    fontSize: '12px',
                                    backgroundColor: copiedUrl === `format-${format.format_id}` ? '#4CAF50' : '#6c757d',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  {copiedUrl === `format-${format.format_id}` ? '✓ Copied' : 'Copy URL'}
                                </button>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {result.extraction_time && (
              <p className="extraction-time">
                Extracted in {result.extraction_time.toFixed(2)}s
              </p>
            )}

            <button onClick={handleReset} className="reset-btn">
              Extract Another Video
            </button>
          </div>
        )}

        {appState === 'error' && (
          <div className="error-section">
            <AlertCircle size={48} className="error-icon" />
            <h2>Extraction Failed</h2>
            <p className="error-detail">{error}</p>
            <button onClick={handleReset} className="reset-btn">
              Try Again
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>YouTube Direct Link Extractor &copy; 2024</p>
      </footer>
    </div>
  );
}

export default App;
