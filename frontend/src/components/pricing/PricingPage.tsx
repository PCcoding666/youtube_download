import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Youtube,
  ArrowLeft,
  Sparkles,
  Coins,
  Download,
  CheckCircle2,
  Clock,
  History,
  AlertCircle,
  ExternalLink,
  DollarSign,
} from 'lucide-react';
import LanguageSwitcher from '../LanguageSwitcher';
import {
  getCreditPackages,
  createCreditCheckout,
  getCreditBalance,
  getCreditTransactions,
} from '../../api';
import type { CreditTransaction, CreditPackagesInfo } from '../../api';

interface PricingPageProps {
  onBack: () => void;
  onSelectPlan: (plan: string) => void;
  isAuthenticated: boolean;
  currentPlan?: string;
}

function PricingPage({ onBack, onSelectPlan: _onSelectPlan, isAuthenticated }: PricingPageProps) {
  const { t } = useTranslation();
  const [packagesInfo, setPackagesInfo] = useState<CreditPackagesInfo | null>(null);
  const [balance, setBalance] = useState<number>(0);
  const [transactions, setTransactions] = useState<CreditTransaction[]>([]);
  const [customAmount, setCustomAmount] = useState<number>(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const creditsPerSgd = packagesInfo?.credits_per_sgd || 5;
  const minAmount = packagesInfo?.min_amount || 1;
  const suggestedAmounts = packagesInfo?.suggested_amounts || [1, 5, 10, 20, 50];

  useEffect(() => {
    loadPackages();
    if (isAuthenticated) {
      loadBalance();
    }
  }, [isAuthenticated]);

  const loadPackages = async () => {
    try {
      const data = await getCreditPackages();
      setPackagesInfo(data);
      setCustomAmount(data.suggested_amount || 10);
    } catch {
      // defaults already set
    }
  };

  const loadBalance = async () => {
    try {
      const data = await getCreditBalance();
      setBalance(data.credit_balance);
    } catch {
      // ignore
    }
  };

  const loadTransactions = async () => {
    try {
      const data = await getCreditTransactions(20);
      setTransactions(data.transactions);
      setBalance(data.credit_balance);
    } catch {
      // ignore
    }
  };

  const handleRecharge = async () => {
    if (!isAuthenticated) {
      setError(t('credits.pleaseLogin', 'Please login first to recharge credits'));
      return;
    }

    if (customAmount < minAmount || !Number.isInteger(customAmount)) {
      setError(t('credits.invalidAmount', `Amount must be an integer >= S$${minAmount}`));
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await createCreditCheckout(customAmount);
      const creditAmount = customAmount * creditsPerSgd;

      if (result.success && result.checkout_url) {
        // Redirect to LemonSqueezy checkout
        window.open(result.checkout_url, '_blank');
        setSuccess(t('credits.redirecting', 'Redirecting to payment page...'));
      } else if (result.success && !result.checkout_url) {
        // Dev mode: direct recharge
        setSuccess(t('credits.rechargeSuccess', `Recharged successfully! +${creditAmount} credits`));
        await loadBalance();
      } else {
        setError(result.message || t('credits.rechargeFailed', 'Recharge failed'));
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || t('credits.rechargeFailed', 'Recharge failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pricing-page">
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

      {/* Hero Section */}
      <section className="pricing-hero">
        <div className="hero-badge">
          <Sparkles size={16} />
          <span>{t('credits.heroTag', 'Pay As You Go')}</span>
        </div>
        <h2 className="hero-title">{t('credits.heroTitle', 'Credit Recharge')}</h2>
        <p className="hero-subtitle">
          {t('credits.heroSubtitle', 'S$1 = 5 Credits. Each download costs 1 credit. Custom amount, no subscription.')}
        </p>

        {/* Balance Display */}
        {isAuthenticated && (
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem 2rem',
            background: 'rgba(59, 130, 246, 0.15)',
            borderRadius: '12px',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            marginTop: '1rem',
          }}>
            <Coins size={24} style={{ color: '#fbbf24' }} />
            <span style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>
              {balance}
            </span>
            <span style={{ color: 'rgba(255,255,255,0.7)' }}>Credits</span>
          </div>
        )}
      </section>

      {/* Custom Amount Recharge */}
      <section style={{ maxWidth: '600px', margin: '0 auto', padding: '0 1.5rem 2rem' }}>
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.08)',
          padding: '2rem',
        }}>
          <h3 style={{ color: '#fff', marginBottom: '1.5rem', textAlign: 'center', fontSize: '1.25rem' }}>
            <DollarSign size={22} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
            {t('credits.customAmount', 'Choose Amount')}
          </h3>

          {/* Quick amount buttons */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: '0.75rem',
            justifyContent: 'center', marginBottom: '1.5rem',
          }}>
            {suggestedAmounts.map((amt) => (
              <button
                key={amt}
                onClick={() => setCustomAmount(amt)}
                style={{
                  padding: '0.75rem 1.25rem',
                  borderRadius: '10px',
                  border: customAmount === amt
                    ? '2px solid #3b82f6'
                    : '1px solid rgba(255,255,255,0.15)',
                  background: customAmount === amt
                    ? 'rgba(59, 130, 246, 0.2)'
                    : 'rgba(255,255,255,0.05)',
                  color: customAmount === amt ? '#93c5fd' : 'rgba(255,255,255,0.7)',
                  cursor: 'pointer',
                  fontSize: '1rem',
                  fontWeight: customAmount === amt ? 700 : 400,
                  transition: 'all 0.2s',
                  minWidth: '80px',
                }}
              >
                S${amt}
              </button>
            ))}
          </div>

          {/* Custom input */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '1rem',
            justifyContent: 'center', marginBottom: '1rem',
          }}>
            <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '1.125rem', fontWeight: 600 }}>S$</span>
            <input
              type="number"
              min={minAmount}
              step={1}
              value={customAmount}
              onChange={(e) => {
                const v = parseInt(e.target.value);
                if (!isNaN(v) && v >= 0) setCustomAmount(v);
              }}
              style={{
                width: '120px', padding: '0.75rem 1rem',
                background: 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '10px', color: '#fff',
                fontSize: '1.5rem', fontWeight: 700,
                textAlign: 'center', outline: 'none',
              }}
            />
            <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem' }}>
              = <strong style={{ color: '#fbbf24', fontSize: '1.125rem' }}>{customAmount * creditsPerSgd}</strong> Credits
            </span>
          </div>

          <p style={{
            textAlign: 'center', color: 'rgba(255,255,255,0.4)',
            fontSize: '0.8125rem', marginBottom: '1.5rem',
          }}>
            {t('credits.rateInfo', `Min S$${minAmount} · 1 SGD = ${creditsPerSgd} Credits · Integer only`)}
          </p>

          {/* Recharge Button */}
          <button
            onClick={handleRecharge}
            disabled={loading || customAmount < minAmount}
            style={{
              width: '100%', padding: '1rem',
              background: loading ? 'rgba(255,255,255,0.1)' : 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
              color: '#fff', border: 'none', borderRadius: '12px',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '1.125rem', fontWeight: 700,
              opacity: loading ? 0.7 : 1,
              transition: 'all 0.2s',
            }}
          >
            {loading
              ? t('credits.processing', 'Processing...')
              : isAuthenticated
                ? `${t('credits.rechargeNow', 'Recharge Now')} · S$${customAmount} → ${customAmount * creditsPerSgd} Credits`
                : t('credits.loginToRecharge', 'Login to Recharge')
            }
          </button>
        </div>
      </section>

      {/* Messages */}
      {error && (
        <div style={{
          maxWidth: '600px', margin: '0 auto 2rem', padding: '1rem',
          background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <AlertCircle size={20} />
          {error}
        </div>
      )}
      {success && (
        <div style={{
          maxWidth: '600px', margin: '0 auto 2rem', padding: '1rem',
          background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)',
          borderRadius: '8px', color: '#86efac', display: 'flex', alignItems: 'center', gap: '0.5rem',
        }}>
          <CheckCircle2 size={20} />
          {success}
        </div>
      )}

      {/* How it works */}
      <section className="highlights-section">
        <h3 className="section-title">
          <Download size={24} />
          {t('credits.howItWorks', 'How Credits Work')}
        </h3>
        <div className="highlights-grid">
          <div className="highlight-card">
            <div className="highlight-icon"><Coins size={32} /></div>
            <h4>{t('credits.step1Title', 'Recharge')}</h4>
            <p>{t('credits.step1Desc', 'S$1 = 5 credits. Custom amount, pay via LemonSqueezy.')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon"><Download size={32} /></div>
            <h4>{t('credits.step2Title', 'Download')}</h4>
            <p>{t('credits.step2Desc', 'Each successful video download costs 1 credit. Failed downloads are free.')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon"><ExternalLink size={32} /></div>
            <h4>{t('credits.step3Title', 'API Access')}</h4>
            <p>{t('credits.step3Desc', 'Generate API keys to use credits programmatically via our Skill API.')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon"><Clock size={32} /></div>
            <h4>{t('credits.step4Title', 'No Expiry')}</h4>
            <p>{t('credits.step4Desc', 'Credits never expire. Use them whenever you need, no monthly limits.')}</p>
          </div>
        </div>
      </section>

      {/* Transaction History */}
      {isAuthenticated && (
        <section style={{ maxWidth: '800px', margin: '0 auto', padding: '0 1.5rem 3rem' }}>
          <button
            onClick={() => {
              setShowHistory(!showHistory);
              if (!showHistory) loadTransactions();
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
              color: '#fff', padding: '0.75rem 1.5rem', borderRadius: '8px',
              cursor: 'pointer', fontSize: '1rem', margin: '0 auto',
            }}
          >
            <History size={20} />
            {showHistory
              ? t('credits.hideHistory', 'Hide Transaction History')
              : t('credits.showHistory', 'Show Transaction History')}
          </button>

          {showHistory && (
            <div style={{ marginTop: '1rem' }}>
              {transactions.length === 0 ? (
                <p style={{ textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                  {t('credits.noTransactions', 'No transactions yet')}
                </p>
              ) : (
                <div style={{
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '12px',
                  border: '1px solid rgba(255,255,255,0.08)',
                  overflow: 'hidden',
                }}>
                  {transactions.map((tx) => (
                    <div key={tx.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '0.75rem 1rem',
                      borderBottom: '1px solid rgba(255,255,255,0.05)',
                    }}>
                      <div>
                        <span style={{
                          color: tx.amount > 0 ? '#86efac' : '#fca5a5',
                          fontWeight: 600,
                          marginRight: '0.75rem',
                        }}>
                          {tx.amount > 0 ? '+' : ''}{tx.amount}
                        </span>
                        <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.875rem' }}>
                          {tx.description}
                        </span>
                      </div>
                      <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem' }}>
                        {new Date(tx.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Footer */}
      <footer className="pricing-footer">
        <p>{t('credits.footer', 'Credits are non-refundable. Contact support for assistance.')}</p>
      </footer>
    </div>
  );
}

export default PricingPage;
