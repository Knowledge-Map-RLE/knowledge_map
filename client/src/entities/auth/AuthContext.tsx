import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authService } from '../../services/auth';
import type { User } from '../user';

/** Событие, которое отправляет любой компонент, запросивший авторизацию
 *  (используется, например, при гейтинге редактирования для неавторизованных).
 *  Виджет User слушает его и открывает модалку входа. */
export const AUTH_LOGIN_EVENT = 'km:open-login';

export const AUTH_GATE_MESSAGE =
    'Зарегистрируйтесь и войдите, чтобы редактировать и использовать AI функции';

interface AuthContextType {
    user: User | null;
    isAuthLoading: boolean;
    isAuthenticated: boolean;
    setUser: (user: User | null) => void;
    logout: () => Promise<void>;
    refresh: () => Promise<void>;
    requestLogin: () => void;
    requestRegister: () => void;
    getToken: () => string | null;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isAuthLoading, setIsAuthLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                const u = await authService.verifyToken();
                if (!cancelled) setUser(u);
            } catch {
                if (!cancelled) setUser(null);
            } finally {
                if (!cancelled) setIsAuthLoading(false);
            }
        })();
        return () => {
            cancelled = true;
        };
    }, []);

    const logout = useCallback(async () => {
        await authService.logout();
        setUser(null);
    }, []);

    const refresh = useCallback(async () => {
        const u = await authService.verifyToken();
        setUser(u);
    }, []);

    const requestLogin = useCallback(() => {
        window.dispatchEvent(new CustomEvent(AUTH_LOGIN_EVENT, { detail: { modal: 'login' } }));
    }, []);

    const requestRegister = useCallback(() => {
        window.dispatchEvent(new CustomEvent(AUTH_LOGIN_EVENT, { detail: { modal: 'register' } }));
    }, []);

    const getToken = useCallback(() => authService.getToken(), []);

    const value = useMemo<AuthContextType>(
        () => ({
            user,
            isAuthLoading,
            isAuthenticated: !!user,
            setUser,
            logout,
            refresh,
            requestLogin,
            requestRegister,
            getToken,
        }),
        [user, isAuthLoading, logout, refresh, requestLogin, requestRegister, getToken],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
