import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Youtube,
  Check,
  Zap,
  Crown,
  Rocket,
  Gift,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  Sparkles,
  Shield,
  Clock,
  Download,
  Film,
  Headphones,
} from 'lucide-react';
import LanguageSwitcher from '../LanguageSwitcher';

interface PricingPageProps {
  onBack: () => void;
  onSelectPlan: (plan: string) => void;
  isAuthenticated: boolean;
  currentPlan?: string;
}

interface PlanFeature {
  textKey: string;
  included: boolean;
  highlight?: boolean;
}

interface PricingPlan {
  id: string;
  nameKey: string;
  descKey: string;
  buttonKey: string;
  monthlyPrice: number;
  yearlyPrice?: number;
  features: PlanFeature[];
  icon: React.ReactNode;
  popular?: boolean;
  gradient: string;
}

function PricingPage({ onBack, onSelectPlan, isAuthenticated, currentPlan }: PricingPageProps) {
  const { t } = useTranslation();
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);

  const plans: PricingPlan[] = [
    {
      id: 'free',
      nameKey: 'pricing.plans.free.name',
      descKey: 'pricing.plans.free.description',
      buttonKey: 'pricing.plans.free.button',
      monthlyPrice: 0,
      features: [
        { textKey: 'pricing.features.downloads3', included: true },
        { textKey: 'pricing.features.quality720', included: true },
        { textKey: 'pricing.features.speedBasic', included: true },
        { textKey: 'pricing.features.supportCommunity', included: true },
        { textKey: 'pricing.features.no1080p', included: false },
        { textKey: 'pricing.features.no4k', included: false },
        { textKey: 'pricing.features.noPriorityQueue', included: false },
      ],
      icon: <Gift size={28} />,
      gradient: 'linear-gradient(135deg, #374151 0%, #1f2937 100%)',
    },
    {
      id: 'basic',
      nameKey: 'pricing.plans.basic.name',
      descKey: 'pricing.plans.basic.description',
      buttonKey: 'pricing.plans.basic.button',
      monthlyPrice: 29,
      yearlyPrice: 290,
      features: [
        { textKey: 'pricing.features.downloads50', included: true, highlight: true },
        { textKey: 'pricing.features.quality1080', included: true, highlight: true },
        { textKey: 'pricing.features.speedStandard', included: true },
        { textKey: 'pricing.features.supportEmail', included: true },
        { textKey: 'pricing.features.history', included: true },
        { textKey: 'pricing.features.no4k', included: false },
        { textKey: 'pricing.features.noPriorityQueue', included: false },
      ],
      icon: <Zap size={28} />,
      gradient: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
    },
    {
      id: 'pro',
      nameKey: 'pricing.plans.pro.name',
      descKey: 'pricing.plans.pro.description',
      buttonKey: 'pricing.plans.pro.button',
      monthlyPrice: 69,
      yearlyPrice: 690,
      features: [
        { textKey: 'pricing.features.downloads200', included: true, highlight: true },
        { textKey: 'pricing.features.quality4k', included: true, highlight: true },
        { textKey: 'pricing.features.speedHigh', included: true, highlight: true },
        { textKey: 'pricing.features.priorityQueue', included: true },
        { textKey: 'pricing.features.batch', included: true },
        { textKey: 'pricing.features.supportPriority', included: true },
        { textKey: 'pricing.features.history', included: true },
      ],
      icon: <Crown size={28} />,
      popular: true,
      gradient: 'linear-gradient(135deg, #ff3b3b 0%, #dc2626 100%)',
    },
    {
      id: 'unlimited',
      nameKey: 'pricing.plans.unlimited.name',
      descKey: 'pricing.plans.unlimited.description',
      buttonKey: 'pricing.plans.unlimited.button',
      monthlyPrice: 149,
      yearlyPrice: 999,
      features: [
        { textKey: 'pricing.features.downloadsUnlimited', included: true, highlight: true },
        { textKey: 'pricing.features.quality4k', included: true, highlight: true },
        { textKey: 'pricing.features.speedUltra', included: true, highlight: true },
        { textKey: 'pricing.features.priorityQueue', included: true },
        { textKey: 'pricing.features.batch', included: true },
        { textKey: 'pricing.features.api', included: true },
        { textKey: 'pricing.features.support1on1', included: true, highlight: true },
      ],
      icon: <Rocket size={28} />,
      gradient: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)',
    },
  ];

  const faqs = [
    { questionKey: 'pricing.faq.q1', answerKey: 'pricing.faq.a1' },
    { questionKey: 'pricing.faq.q2', answerKey: 'pricing.faq.a2' },
    { questionKey: 'pricing.faq.q3', answerKey: 'pricing.faq.a3' },
    { questionKey: 'pricing.faq.q4', answerKey: 'pricing.faq.a4' },
    { questionKey: 'pricing.faq.q5', answerKey: 'pricing.faq.a5' },
  ];

  const comparisonFeatures = [
    { nameKey: 'pricing.comparison.monthlyDownloads', free: '3', basic: '50', pro: '200', unlimited: '∞' },
    { nameKey: 'pricing.comparison.maxQuality', free: '720p', basic: '1080p', pro: '4K', unlimited: '4K' },
    { nameKey: 'pricing.comparison.downloadSpeed', freeKey: 'pricing.comparison.basic', basicKey: 'pricing.comparison.standard', proKey: 'pricing.comparison.high', unlimitedKey: 'pricing.comparison.ultra' },
    { nameKey: 'pricing.comparison.priority', free: '—', basic: '—', pro: '✓', unlimitedKey: 'pricing.comparison.highestPriority' },
    { nameKey: 'pricing.comparison.batchDownload', free: '—', basic: '—', pro: '✓', unlimited: '✓' },
    { nameKey: 'pricing.comparison.apiAccess', free: '—', basic: '—', pro: '—', unlimited: '✓' },
    { nameKey: 'pricing.comparison.support', freeKey: 'pricing.comparison.community', basicKey: 'pricing.comparison.email', proKey: 'pricing.comparison.prioritySupport', unlimitedKey: 'pricing.comparison.dedicated' },
  ];

  const handleSelectPlan = (planId: string) => {
    if (planId === 'free') {
      onBack();
      return;
    }
    onSelectPlan(planId);
  };

  const getButtonText = (plan: PricingPlan) => {
    if (currentPlan === plan.id) return t('pricing.currentPlan');
    if (plan.id === 'free') return t(plan.buttonKey);
    if (!isAuthenticated) return t('pricing.loginToSubscribe');
    return t(plan.buttonKey);
  };

  const getPrice = (plan: PricingPlan) => {
    if (plan.monthlyPrice === 0) return '¥0';
    if (billingCycle === 'yearly' && plan.yearlyPrice) {
      return `¥${plan.yearlyPrice}`;
    }
    return `¥${plan.monthlyPrice}`;
  };

  const getPeriod = (plan: PricingPlan) => {
    if (plan.monthlyPrice === 0) return '/∞';
    return billingCycle === 'yearly' ? `/${t('common.year')}` : `/${t('common.month')}`;
  };

  const getSavings = (plan: PricingPlan) => {
    if (!plan.yearlyPrice || plan.monthlyPrice === 0) return null;
    const yearlyCost = plan.monthlyPrice * 12;
    const savings = yearlyCost - plan.yearlyPrice;
    if (savings > 0) {
      return `${t('payment.save').replace('¥20', '')}¥${savings}`;
    }
    return null;
  };

  const getComparisonValue = (feature: any, key: string) => {
    const valueKey = feature[`${key}Key`];
    if (valueKey) {
      return t(valueKey);
    }
    return feature[key] || '—';
  };

  return (
    <div className="pricing-page">
      {/* Header */}
      <header className="pricing-header">
        <div className="pricing-header-content">
          <button onClick={onBack} className="back-button">
            <ArrowLeft size={20} />
            <span>{t('common.back')}</span>
          </button>
          <div className="pricing-logo">
            <Youtube size={32} />
            <h1>{t('common.appName')}</h1>
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
          <span>{t('pricing.heroTag')}</span>
        </div>
        <h2 className="hero-title">{t('pricing.heroTitle')}</h2>
        <p className="hero-subtitle">
          {t('pricing.heroSubtitle')}
        </p>

        {/* Billing Toggle */}
        <div className="billing-toggle">
          <button
            className={`toggle-btn ${billingCycle === 'monthly' ? 'active' : ''}`}
            onClick={() => setBillingCycle('monthly')}
          >
            {t('pricing.monthly')}
          </button>
          <button
            className={`toggle-btn ${billingCycle === 'yearly' ? 'active' : ''}`}
            onClick={() => setBillingCycle('yearly')}
          >
            {t('pricing.yearly')}
            <span className="discount-badge">{t('pricing.savePercent')}</span>
          </button>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pricing-cards-section">
        <div className="pricing-cards-grid">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className={`pricing-card ${plan.popular ? 'popular' : ''} ${currentPlan === plan.id ? 'current' : ''}`}
            >
              {plan.popular && (
                <div className="popular-badge">
                  <Crown size={14} />
                  {t('pricing.mostPopular')}
                </div>
              )}
              {currentPlan === plan.id && (
                <div className="current-badge">{t('pricing.currentPlan')}</div>
              )}
              
              <div className="card-icon" style={{ background: plan.gradient }}>
                {plan.icon}
              </div>
              
              <h3 className="card-title">{t(plan.nameKey)}</h3>
              <p className="card-description">{t(plan.descKey)}</p>
              
              <div className="card-price">
                <span className="price-amount">{getPrice(plan)}</span>
                <span className="price-period">{getPeriod(plan)}</span>
              </div>
              
              {billingCycle === 'yearly' && getSavings(plan) && (
                <div className="savings-badge">{getSavings(plan)}</div>
              )}
              
              <ul className="card-features">
                {plan.features.map((feature, index) => (
                  <li
                    key={index}
                    className={`feature-item ${!feature.included ? 'disabled' : ''} ${feature.highlight ? 'highlight' : ''}`}
                  >
                    <Check size={16} className={feature.included ? 'check-icon' : 'check-icon disabled'} />
                    <span>{t(feature.textKey)}</span>
                  </li>
                ))}
              </ul>
              
              <button
                className={`card-button ${plan.popular ? 'popular-btn' : ''}`}
                style={plan.popular ? { background: plan.gradient } : {}}
                onClick={() => handleSelectPlan(plan.id)}
                disabled={currentPlan === plan.id}
              >
                {getButtonText(plan)}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Features Comparison Table */}
      <section className="comparison-section">
        <h3 className="section-title">
          <Film size={24} />
          {t('pricing.comparison.title')}
        </h3>
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>{t('pricing.comparison.feature')}</th>
                <th>{t('pricing.comparison.free')}</th>
                <th>{t('pricing.comparison.basic')}</th>
                <th className="highlight-col">{t('pricing.comparison.pro')}</th>
                <th>{t('pricing.comparison.unlimited')}</th>
              </tr>
            </thead>
            <tbody>
              {comparisonFeatures.map((feature, index) => (
                <tr key={index}>
                  <td className="feature-name">{t(feature.nameKey)}</td>
                  <td>{getComparisonValue(feature, 'free')}</td>
                  <td>{getComparisonValue(feature, 'basic')}</td>
                  <td className="highlight-col">{getComparisonValue(feature, 'pro')}</td>
                  <td>{getComparisonValue(feature, 'unlimited')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Features Highlights */}
      <section className="highlights-section">
        <h3 className="section-title">
          <Shield size={24} />
          {t('pricing.highlights.title')}
        </h3>
        <div className="highlights-grid">
          <div className="highlight-card">
            <div className="highlight-icon">
              <Download size={32} />
            </div>
            <h4>{t('pricing.highlights.speed.title')}</h4>
            <p>{t('pricing.highlights.speed.desc')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon">
              <Film size={32} />
            </div>
            <h4>{t('pricing.highlights.quality.title')}</h4>
            <p>{t('pricing.highlights.quality.desc')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon">
              <Headphones size={32} />
            </div>
            <h4>{t('pricing.highlights.audio.title')}</h4>
            <p>{t('pricing.highlights.audio.desc')}</p>
          </div>
          <div className="highlight-card">
            <div className="highlight-icon">
              <Clock size={32} />
            </div>
            <h4>{t('pricing.highlights.processing.title')}</h4>
            <p>{t('pricing.highlights.processing.desc')}</p>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="faq-section">
        <h3 className="section-title">
          <Sparkles size={24} />
          {t('pricing.faq.title')}
        </h3>
        <div className="faq-list">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className={`faq-item ${expandedFaq === index ? 'expanded' : ''}`}
            >
              <button
                className="faq-question"
                onClick={() => setExpandedFaq(expandedFaq === index ? null : index)}
              >
                <span>{t(faq.questionKey)}</span>
                {expandedFaq === index ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
              </button>
              <div className="faq-answer">
                <p>{t(faq.answerKey)}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <div className="cta-content">
          <h3>{t('pricing.cta.title')}</h3>
          <p>{t('pricing.cta.desc')}</p>
          <button className="cta-button" onClick={onBack}>
            {t('pricing.cta.button')}
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="pricing-footer">
        <p>{t('pricing.footer')}</p>
      </footer>
    </div>
  );
}

export default PricingPage;
