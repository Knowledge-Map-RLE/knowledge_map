import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import s from './Toast.module.css';

export type ToastType = 'error' | 'success' | 'info';

export interface ToastItem {
    id: number;
    message: string;
    type: ToastType;
}

interface ToastContextType {
    showToast: (message: string, type?: ToastType, duration?: number) => void;
    error: (message: string, duration?: number) => void;
    success: (message: string, duration?: number) => void;
    info: (message: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<ToastItem[]>([]);

    const dismiss = useCallback((id: number) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const showToast = useCallback(
        (message: string, type: ToastType = 'info', duration: number = 3500) => {
            const id = ++toastId;
            setToasts((prev) => [...prev, { id, message, type }]);
            if (duration > 0) {
                window.setTimeout(() => dismiss(id), duration);
            }
        },
        [dismiss],
    );

    const error = useCallback(
        (message: string, duration?: number) => showToast(message, 'error', duration),
        [showToast],
    );
    const success = useCallback(
        (message: string, duration?: number) => showToast(message, 'success', duration),
        [showToast],
    );
    const info = useCallback(
        (message: string, duration?: number) => showToast(message, 'info', duration),
        [showToast],
    );

    const value = useMemo<ToastContextType>(
        () => ({ showToast, error, success, info }),
        [showToast, error, success, info],
    );

    return (
        <ToastContext.Provider value={value}>
            {children}
            <div className={s.toastWrap} aria-live="polite">
                {toasts.map((t) => (
                    <div
                        key={t.id}
                        className={`${s.toast} ${t.type === 'error' ? s.error : t.type === 'success' ? s.success : s.info}`}
                        onClick={() => dismiss(t.id)}
                    >
                        {t.message}
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast(): ToastContextType {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
}
