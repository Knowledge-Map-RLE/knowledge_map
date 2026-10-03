import { useTranslation } from 'react-i18next';
import i18n, { LANGUAGE_STORAGE_KEY, type SupportedLanguage } from './index';

export default function LanguageSwitcher({ className = '' }: { className?: string }) {
    const { t } = useTranslation();
    const language: SupportedLanguage = i18n.resolvedLanguage === 'ru' ? 'ru' : 'en';

    const changeLanguage = async (nextLanguage: SupportedLanguage) => {
        await i18n.changeLanguage(nextLanguage);
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage);
    };

    return (
        <label className={className}>
            <select
                aria-label={t('common.language.label')}
                title={t('common.language.label')}
                value={language}
                onChange={event => void changeLanguage(event.target.value as SupportedLanguage)}
            >
                <option value="ru">{t('common.language.russian')}</option>
                <option value="en">{t('common.language.english')}</option>
            </select>
        </label>
    );
}
