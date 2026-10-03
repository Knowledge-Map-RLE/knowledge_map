import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import english from './locales/en.json';
import russian from './locales/ru.json';

export const LANGUAGE_STORAGE_KEY = 'knowledge-map.language';
export const SUPPORTED_LANGUAGES = ['ru', 'en'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

function isSupportedLanguage(value: string | null): value is SupportedLanguage {
    return value !== null && SUPPORTED_LANGUAGES.includes(value as SupportedLanguage);
}

function initialLanguage(): SupportedLanguage {
    if (typeof window === 'undefined') return 'ru';

    const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isSupportedLanguage(saved)) return saved;

    const browserLanguages = window.navigator.languages?.length
        ? window.navigator.languages
        : [window.navigator.language];
    return browserLanguages.some(language => language.toLowerCase().startsWith('ru')) ? 'ru' : 'en';
}

void i18n.use(initReactI18next).init({
    resources: {
        en: { translation: english },
        ru: { translation: russian },
    },
    lng: initialLanguage(),
    fallbackLng: false,
    supportedLngs: [...SUPPORTED_LANGUAGES],
    load: 'languageOnly',
    keySeparator: '.',
    interpolation: { escapeValue: false },
    returnNull: false,
    returnEmptyString: false,
    saveMissing: import.meta.env.DEV,
    missingKeyHandler: (_languages, _namespace, key) => {
        if (import.meta.env.DEV) console.error(`[i18n] Нет перевода для ключа: ${key}`);
    },
});

if (typeof document !== 'undefined') {
    document.documentElement.lang = initialLanguage();
    i18n.on('languageChanged', language => {
        document.documentElement.lang = language;
    });
}

export default i18n;
