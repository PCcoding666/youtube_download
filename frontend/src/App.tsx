import { useState, useEffect, useCallback } from 'react';
import {
  Youtube,
  Download,
  FileText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Play,
  Clock,
  User,
  Link,
  Volume2,
} from 'lucide-react';
import {
  processVideo,
  getTaskStatus,
  getTaskResult,
  getSubtitleDownloadUrl,
  healthCheck,
} from './api';
import type { TaskResult, TranscriptSegment, VideoResolution } from './api';
import './App.css';

type AppState = 'idle' | 'processing' | 'completed' | 'error';

function App() {
  const [url, setUrl] = useState('');
  const [enableTranscription, setEnableTranscription] = useState(true);
  const [resolution, setResolution] = useState<VideoResolution>('720');
  const [appState, setAppState] = useState<AppState>('idle');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [result, setResult] = useState<TaskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isApiHealthy, setIsApiHealthy] = useState<boolean | null>(null);

  // Check API health on mount
  useEffect(() => {
    const checkHealth = async () => {
      const healthy = await healthCheck();
      setIsApiHealthy(healthy);
    };
    checkHealth();
  }, []);

  // Poll task status
  const pollStatus = useCallback(async (id: string) => {
    try {
      const status = await getTaskStatus(id);
      setProgress(status.progress);
      setStatusMessage(getStatusMessage(status.status));

      if (status.status === 'completed') {
        const taskResult = await getTaskResult(id);
        setResult(taskResult);
        setAppState('completed');
      } else if (status.status === 'failed') {
        setError(status.error_message || 'Processing failed');
        setAppState('error');
      } else {
        // Continue polling
        setTimeout(() => pollStatus(id), 2000);
      }
    } catch (err) {
      setError('Failed to get task status');
      setAppState('error');
    }
  }, []);

  const getStatusMessage = (status: string): string => {
    const messages: Record<string, string> = {
      pending: 'Preparing...',
      downloading: 'Downloading video from YouTube...',
      extracting_audio: 'Extracting audio...',
      uploading: 'Uploading to cloud storage...',
      transcribing: 'Transcribing audio...',
      completed: 'Processing complete!',
      failed: 'Processing failed',
    };
    return messages[status] || status;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!url.trim()) {
      setError('Please enter a YouTube URL');
      return;
    }

    // Reset state
    setError(null);
    setResult(null);
    setProgress(0);
    setAppState('processing');
    setStatusMessage('Submitting task...');

    try {
      const response = await processVideo({
        youtube_url: url,
        enable_transcription: enableTranscription,
        resolution: resolution,
      });

      setTaskId(response.task_id);
      pollStatus(response.task_id);
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Failed to submit task';
      setError(errorMessage);
      setAppState('error');
    }
  };

  const handleReset = () => {
    setUrl('');
    setAppState('idle');
    setTaskId(null);
    setProgress(0);
    setStatusMessage('');
    setResult(null);
    setError(null);
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 100);
    return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
  };

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <Youtube size={32} />
          <h1>YouTube Transcriber</h1>
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
            <h2>Download & Transcribe YouTube Videos</h2>
            <p className="subtitle">
              Enter a YouTube URL to download the video and automatically transcribe the audio.
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
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={enableTranscription}
                    onChange={(e) => setEnableTranscription(e.target.checked)}
                  />
                  <FileText size={16} />
                  Enable Audio Transcription
                </label>
                
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
                    <option value="audio">Audio Only (MP3)</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="submit-btn"
                disabled={!isApiHealthy || !url.trim()}
              >
                <Download size={20} />
                Start Processing
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

        {appState === 'processing' && (
          <div className="processing-section">
            <div className="processing-icon">
              <Loader2 size={48} className="spinning" />
            </div>
            <h2>{statusMessage}</h2>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <p className="progress-text">{progress}% complete</p>
          </div>
        )}

        {appState === 'completed' && result && (
          <div className="result-section">
            <div className="success-header">
              <CheckCircle2 size={48} className="success-icon" />
              <h2>Processing Complete!</h2>
            </div>

            <div className="video-info">
              <h3>{result.video_title || 'Video'}</h3>
              <div className="video-meta">
                <span>
                  <Clock size={16} />
                  {formatDuration(result.video_duration)}
                </span>
              </div>
            </div>

            <div className="download-buttons">
              {result.video_url && (
                <a
                  href={result.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="download-btn video-btn"
                >
                  <Play size={20} />
                  Download Video
                </a>
              )}
              {result.audio_url && (
                <a
                  href={result.audio_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="download-btn audio-btn"
                >
                  <Volume2 size={20} />
                  Download Audio
                </a>
              )}
              {result.transcript && taskId && (
                <a
                  href={getSubtitleDownloadUrl(taskId)}
                  className="download-btn subtitle-btn"
                >
                  <FileText size={20} />
                  Download Subtitles (SRT)
                </a>
              )}
            </div>

            {result.transcript && result.transcript.length > 0 && (
              <div className="transcript-section">
                <h3>
                  <FileText size={20} />
                  Transcript ({result.transcript.length} segments)
                </h3>
                <div className="transcript-list">
                  {result.transcript.map((segment: TranscriptSegment, index: number) => (
                    <div key={index} className="transcript-item">
                      <div className="transcript-time">
                        {formatTime(segment.start_time)} - {formatTime(segment.end_time)}
                      </div>
                      {segment.speaker_id !== null && (
                        <div className="transcript-speaker">
                          <User size={14} />
                          Speaker {segment.speaker_id + 1}
                        </div>
                      )}
                      <div className="transcript-text">{segment.text}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.full_text && (
              <div className="full-text-section">
                <h3>Full Text</h3>
                <div className="full-text">{result.full_text}</div>
              </div>
            )}

            <button onClick={handleReset} className="reset-btn">
              Process Another Video
            </button>
          </div>
        )}

        {appState === 'error' && (
          <div className="error-section">
            <AlertCircle size={48} className="error-icon" />
            <h2>Processing Failed</h2>
            <p className="error-detail">{error}</p>
            <button onClick={handleReset} className="reset-btn">
              Try Again
            </button>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>YouTube Video Transcriber MVP &copy; 2024</p>
      </footer>
    </div>
  );
}

export default App;
