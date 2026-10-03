/**
 * Хранение JWT-токена.
 *
 * При выборе «Запомнить меня» токен кладётся в localStorage и переживает
 * перезапуск браузера. Без галочки — в sessionStorage (живёт до закрытия вкладки).
 */

const LOCAL_STORAGE_KEY = 'auth_token';
const SESSION_STORAGE_KEY = 'auth_token_session';

export const AUTH_SESSION_INVALIDATED_EVENT = 'km:auth-session-invalidated';

export function saveToken(token: string, remember: boolean): void {
    clearToken();
    if (remember) {
        localStorage.setItem(LOCAL_STORAGE_KEY, token);
    } else {
        sessionStorage.setItem(SESSION_STORAGE_KEY, token);
    }
}

export function getToken(): string | null {
    return localStorage.getItem(LOCAL_STORAGE_KEY) ?? sessionStorage.getItem(SESSION_STORAGE_KEY);
}

export function clearToken(): void {
    localStorage.removeItem(LOCAL_STORAGE_KEY);
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
}

/** Invalidate only the session used by the rejected request, preserving a newer login. */
export function invalidateToken(expectedToken: string): void {
    if (getToken() !== expectedToken) return;
    clearToken();
    window.dispatchEvent(new Event(AUTH_SESSION_INVALIDATED_EVENT));
}
