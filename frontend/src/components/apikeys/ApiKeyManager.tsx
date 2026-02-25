import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Youtube,
  ArrowLeft,
  Key,
  Plus,
  Trash2,
  Copy,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Shield,
  Clock,
  Coins,
} from 'lucide-react';
import LanguageSwitcher from '../LanguageSwitcher';
import { generateApiKey, listApiKeys, deleteApiKey } from '../../api';
import type { ApiKeyInfo } from '../../api';

interface ApiKeyManagerProps {
  onBack: () => void;
  creditBalance: number;
}

function ApiKeyManager({ onBack, creditBalance }: ApiKeyManagerProps) {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [maxKeys, setMaxKeys] = useState(5);
  const [newKeyName, setNewKeyName] = useState('');
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const data = await listApiKeys();
      setKeys(data.keys);
      setMaxKeys(data.max_keys);
    } catch {
      // ignore
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setGeneratedKey(null);

    try {
      const result = await generateApiKey(newKeyName || undefined);
      if (result.success && result.api_key) {
        setGeneratedKey(result.api_key);
        setNewKeyName('');
        await loadKeys();
      } else {
        setError(result.message);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t('apikeys.generateFailed', 'Failed to generate API Key'));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (keyId: number) => {
    if (!confirm(t('apikeys.confirmDelete', 'Are you sure you want to delete this API Key? This cannot be undone.'))) {
      return;
    }

    try {
      await deleteApiKey(keyId);
      await loadKeys();
    } catch (err: any) {
      setError(err.response?.data?.detail || t('apikeys.deleteFailed', 'Failed to delete API Key'));
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="pricing-page" style={{ minHeight: '100vh' }}>
      {/* Header */}
      <header className="pricing-header">
        <div className="pricing-header-content">
          <button onClick={onBack} className="back-button">
            <ArrowLeft size={20} />
            <span>{t('common.back', 'Back')}</span>
          </button>
          <div className="pricing-logo">
            <Youtube size={32} />
            <h1>{t('common.appName', 'YT Downloader')}</h1>
          </div>
          <div className="header-spacer">
            <LanguageSwitcher />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem 1.5rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <Key size={48} style={{ color: '#3b82f6', marginBottom: '1rem' }} />
          <h2 style={{ color: '#fff', fontSize: '1.75rem', marginBottom: '0.5rem' }}>
            {t('apikeys.title', 'API Key Management')}
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.6)' }}>
            {t('apikeys.subtitle', 'Generate API keys to use our download service programmatically')}
          </p>

          {/* Balance display */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
            padding: '0.5rem 1rem', background: 'rgba(59,130,246,0.1)',
            borderRadius: '8px', border: '1px solid rgba(59,130,246,0.2)',
            marginTop: '1rem',
          }}>
            <Coins size={18} style={{ color: '#fbbf24' }} />
            <span style={{ color: '#fff', fontWeight: 600 }}>{creditBalance}</span>
            <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>credits available</span>
          </div>
        </div>

        {/* Generate New Key */}
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.08)',
          padding: '1.5rem',
          marginBottom: '1.5rem',
        }}>
          <h3 style={{ color: '#fff', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Plus size={20} />
            {t('apikeys.generateNew', 'Generate New API Key')}
          </h3>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <input
              type="text"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder={t('apikeys.keyNamePlaceholder', 'Key name (optional, e.g. "My App")')}
              maxLength={100}
              style={{
                flex: 1, padding: '0.75rem 1rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px', color: '#fff', fontSize: '0.9375rem',
                outline: 'none',
              }}
            />
            <button
              onClick={handleGenerate}
              disabled={loading || keys.length >= maxKeys}
              style={{
                padding: '0.75rem 1.5rem',
                background: keys.length >= maxKeys ? 'rgba(255,255,255,0.1)' : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                color: '#fff', border: 'none', borderRadius: '8px',
                cursor: keys.length >= maxKeys ? 'not-allowed' : 'pointer',
                fontWeight: 600, whiteSpace: 'nowrap',
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? '...' : t('apikeys.generate', 'Generate')}
            </button>
          </div>

          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.8125rem', marginTop: '0.5rem' }}>
            {t('apikeys.keyLimit', `${keys.length}/${maxKeys} keys used`).replace('${used}', String(keys.length)).replace('${max}', String(maxKeys))}
          </p>
        </div>

        {/* Generated Key Display */}
        {generatedKey && (
          <div style={{
            background: 'rgba(34, 197, 94, 0.1)',
            borderRadius: '12px',
            border: '1px solid rgba(34, 197, 94, 0.3)',
            padding: '1.5rem',
            marginBottom: '1.5rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Shield size={20} style={{ color: '#86efac' }} />
              <strong style={{ color: '#86efac' }}>
                {t('apikeys.newKeyGenerated', 'New API Key Generated!')}
              </strong>
            </div>
            <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.875rem', marginBottom: '0.75rem' }}>
              {t('apikeys.saveWarning', 'Copy and save this key now. It will not be shown again!')}
            </p>

            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '0.75rem 1rem',
            }}>
              <code style={{
                flex: 1, color: '#86efac', fontSize: '0.875rem',
                wordBreak: 'break-all', fontFamily: 'monospace',
              }}>
                {showKey ? generatedKey : generatedKey.substring(0, 12) + '•'.repeat(20)}
              </code>
              <button
                onClick={() => setShowKey(!showKey)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.6)', padding: '4px' }}
              >
                {showKey ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
              <button
                onClick={() => copyToClipboard(generatedKey)}
                style={{
                  background: copied ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.1)',
                  border: 'none', cursor: 'pointer', color: copied ? '#86efac' : '#fff',
                  padding: '0.5rem 1rem', borderRadius: '6px',
                  display: 'flex', alignItems: 'center', gap: '0.25rem',
                  fontWeight: 600, fontSize: '0.875rem',
                }}
              >
                {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                {copied ? t('common.copied', 'Copied!') : t('common.copy', 'Copy')}
              </button>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px',
            border: '1px solid rgba(239, 68, 68, 0.3)', padding: '0.75rem 1rem',
            marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem',
            color: '#fca5a5',
          }}>
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        {/* Existing Keys List */}
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.08)',
          overflow: 'hidden',
          marginBottom: '2rem',
        }}>
          <h3 style={{
            color: '#fff', padding: '1rem 1.5rem', margin: 0,
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
          }}>
            <Key size={20} />
            {t('apikeys.yourKeys', 'Your API Keys')}
          </h3>

          {keys.length === 0 ? (
            <p style={{ padding: '2rem', textAlign: 'center', color: 'rgba(255,255,255,0.4)' }}>
              {t('apikeys.noKeys', 'No API keys yet. Generate one above.')}
            </p>
          ) : (
            keys.map((key) => (
              <div key={key.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '1rem 1.5rem',
                borderBottom: '1px solid rgba(255,255,255,0.05)',
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                    <code style={{ color: '#3b82f6', fontFamily: 'monospace', fontSize: '0.875rem' }}>
                      {key.key_prefix}•••••
                    </code>
                    <span style={{
                      padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem',
                      background: key.is_active ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                      color: key.is_active ? '#86efac' : '#fca5a5',
                    }}>
                      {key.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', color: 'rgba(255,255,255,0.4)', fontSize: '0.8125rem' }}>
                    <span>{key.name}</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Clock size={12} />
                      {new Date(key.created_at).toLocaleDateString()}
                    </span>
                    {key.last_used_at && (
                      <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(key.id)}
                  style={{
                    background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
                    color: '#fca5a5', padding: '0.5rem', borderRadius: '6px', cursor: 'pointer',
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Usage Guide */}
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.08)',
          padding: '1.5rem',
        }}>
          <h3 style={{ color: '#fff', marginBottom: '1rem' }}>
            {t('apikeys.usageGuide', 'API Usage Guide')}
          </h3>
          <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.875rem', lineHeight: 1.8 }}>
            <p style={{ marginBottom: '0.75rem' }}>
              <strong style={{ color: '#3b82f6' }}>POST</strong>{' '}
              <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                /api/v1/skill/download
              </code>
            </p>
            <pre style={{
              background: 'rgba(0,0,0,0.3)', padding: '1rem', borderRadius: '8px',
              overflow: 'auto', fontSize: '0.8125rem', lineHeight: 1.6,
            }}>
{`curl -X POST https://your-domain/api/v1/skill/download \\
  -H "Authorization: Bearer sk-yt-xxxxx" \\
  -H "Content-Type: application/json" \\
  -d '{"youtube_url": "https://youtube.com/watch?v=...", "resolution": "720"}'`}
            </pre>
            <p style={{ marginTop: '0.75rem' }}>
              <strong style={{ color: '#3b82f6' }}>GET</strong>{' '}
              <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                /api/v1/skill/balance
              </code>
              {' '}- {t('apikeys.checkBalance', 'Check your credit balance')}
            </p>
            <p style={{ marginTop: '0.5rem' }}>
              <strong style={{ color: '#3b82f6' }}>GET</strong>{' '}
              <code style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                /api/v1/skill/health
              </code>
              {' '}- {t('apikeys.healthCheck', 'Service health check (no auth required)')}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ApiKeyManager;
