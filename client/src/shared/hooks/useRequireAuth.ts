import { useCallback } from 'react';
import { useAuth, AUTH_GATE_MESSAGE } from '../../entities/auth';
import { useToast } from '../ui/Toast';

/**
 * Возвращает функцию-гейт: если пользователь не авторизован — показывает
 * красный toast и открывает модалку входа, возвращает false.
 * Иначе — true (действие разрешено).
 */
export function useRequireAuth(): (message?: string) => boolean {
    const { isAuthenticated, requestLogin } = useAuth();
    const { error } = useToast();

    return useCallback(
        (message?: string) => {
            if (isAuthenticated) return true;
            error(message || AUTH_GATE_MESSAGE);
            requestLogin();
            return false;
        },
        [isAuthenticated, requestLogin, error],
    );
}
