import React from 'react';
import { describe, expect, test, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import CookieConsent from '../ui';

const CONSENT_KEY = 'km_cookie_consent';

describe('CookieConsent', () => {
    beforeEach(() => {
        localStorage.clear();
        cleanup();
    });

    test('при первом заходе плашка отображается', () => {
        render(<CookieConsent />);
        expect(screen.getByRole('dialog', { name: 'Использование cookie' })).toBeInTheDocument();
        expect(screen.getByLabelText('Закрыть уведомление о cookie')).toBeInTheDocument();
    });

    test('после закрытия крестиком плашка исчезает навсегда', () => {
        render(<CookieConsent />);
        fireEvent.click(screen.getByLabelText('Закрыть уведомление о cookie'));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(localStorage.getItem(CONSENT_KEY)).toBe('1');
    });

    test('при повторном заходе (согласие уже сохранено) плашка не показывается', () => {
        localStorage.setItem(CONSENT_KEY, '1');
        render(<CookieConsent />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    test('повторный рендер в том же браузере не показывает плашку снова', () => {
        render(<CookieConsent />);
        fireEvent.click(screen.getByLabelText('Закрыть уведомление о cookie'));
        cleanup();
        render(<CookieConsent />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
});