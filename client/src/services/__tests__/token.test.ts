import { describe, expect, test, beforeEach } from 'vitest';
import { saveToken, getToken, clearToken } from '../token';

const LOCAL_STORAGE_KEY = 'auth_token';
const SESSION_STORAGE_KEY = 'auth_token_session';

describe('token persistence', () => {
    beforeEach(() => {
        localStorage.clear();
        sessionStorage.clear();
    });

    test('saveToken(remember=true) кладёт токен в localStorage и переживает перезапуск браузера', () => {
        saveToken('jwt.remember', true);
        expect(localStorage.getItem(LOCAL_STORAGE_KEY)).toBe('jwt.remember');
        expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
        expect(getToken()).toBe('jwt.remember');
    });

    test('saveToken(remember=false) кладёт токен только в sessionStorage', () => {
        saveToken('jwt.session', false);
        expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe('jwt.session');
        expect(localStorage.getItem(LOCAL_STORAGE_KEY)).toBeNull();
        expect(getToken()).toBe('jwt.session');
    });

    test('последующая запись перезаписывает предыдущее хранилище', () => {
        saveToken('jwt.first', true);
        saveToken('jwt.second', false);
        expect(localStorage.getItem(LOCAL_STORAGE_KEY)).toBeNull();
        expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe('jwt.second');
        expect(getToken()).toBe('jwt.second');
    });

    test('getToken отдаёт null, если токена нет ни в одном хранилище', () => {
        expect(getToken()).toBeNull();
    });

    test('clearToken очищает оба хранилища', () => {
        saveToken('jwt.remember', true);
        saveToken('jwt.session', false);
        clearToken();
        expect(localStorage.getItem(LOCAL_STORAGE_KEY)).toBeNull();
        expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
        expect(getToken()).toBeNull();
    });
});