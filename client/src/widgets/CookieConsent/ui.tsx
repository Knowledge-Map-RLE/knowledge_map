import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ModalPortal } from '../../shared/ui/ModalPortal';
import s from './CookieConsent.module.css';

/**
 * Уведомление об использовании cookie.
 *
 * Показывается один раз при первом заходе на сайт и закрывается крестиком.
 * Согласие хранится в localStorage (`km_cookie_consent`).
 *
 * Аналитика и аутентификация не используют третьи стороны и персональные
 * cookie: токены лежат в Web Storage, счётчики — cookieless (OpenTelemetry),
 * поэтому текст носит информационно-комплаенсный характер.
 */

const CONSENT_KEY = 'km_cookie_consent';

function hasConsent(): boolean {
    try {
        return localStorage.getItem(CONSENT_KEY) === '1';
    } catch {
        return true;
    }
}

function storeConsent(): void {
    try {
        localStorage.setItem(CONSENT_KEY, '1');
    } catch {
        /* localStorage недоступен — плашка просто скрывается на время сессии */
    }
}

const CookieConsent: React.FC = () => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState<boolean>(() => !hasConsent());

    if (!visible) {
        return null;
    }

    const handleClose = () => {
        storeConsent();
        setVisible(false);
    };

    return (
        <ModalPortal>
            <div className={s.overlay} role="dialog" aria-modal="true" aria-label={t('cookieConsent.ariaLabel')}>
                <div className={s.banner}>
                    <div className={s.header}>
                        <h2 className={s.title}>{t('cookieConsent.title')}</h2>
                        <button
                            type="button"
                            onClick={handleClose}
                            className={s.closeButton}
                            aria-label={t('cookieConsent.close')}
                        >
                            ×
                        </button>
                    </div>
                    <div className={s.body}>
                        <p>
                            {t('cookieConsent.description')}
                        </p>
                    </div>
                </div>
            </div>
        </ModalPortal>
    );
};

export default CookieConsent;
