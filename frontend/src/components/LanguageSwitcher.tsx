import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';

function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'zh' : 'en';
    i18n.changeLanguage(newLang);
  };

  return (
    <button
      onClick={toggleLanguage}
      className="language-switcher"
      title={i18n.language === 'en' ? '切换到中文' : 'Switch to English'}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.5rem 0.75rem',
        backgroundColor: 'rgba(99, 102, 241, 0.1)',
        color: '#a5b4fc',
        border: '1px solid rgba(99, 102, 241, 0.3)',
        borderRadius: '8px',
        cursor: 'pointer',
        fontSize: '0.875rem',
        fontWeight: 500,
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'rgba(99, 102, 241, 0.2)';
        e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'rgba(99, 102, 241, 0.1)';
        e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.3)';
      }}
    >
      <Globe size={16} />
      <span>{i18n.language === 'en' ? 'EN' : '中文'}</span>
    </button>
  );
}

export default LanguageSwitcher;
