import { useState, useEffect, useRef } from 'react';
import s from './User.module.css';
import { LoginModal } from './components/LoginModal';
import { RegisterModal } from './components/RegisterModal';
import { RecoveryModal } from './components/RecoveryModal';
import { PasswordResetModal } from './components/PasswordResetModal';
import { authService } from '../../services/auth';
import type { User as UserType } from '../../services/auth';
import type { ModalType, UserProps } from './model';

const User: React.FC<UserProps> = ({ className = '' }) => {
    const [activeModal, setActiveModal] = useState<ModalType>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [userData, setUserData] = useState<UserType | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [menuOpen, setMenuOpen] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        checkAuthStatus();
    }, []);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const checkAuthStatus = async () => {
        try {
            const user = await authService.verifyToken();
            if (user) {
                setIsAuthenticated(true);
                setUserData(user);
            } else {
                setIsAuthenticated(false);
                setUserData(null);
            }
        } catch {
            setIsAuthenticated(false);
            setUserData(null);
        } finally {
            setIsLoading(false);
        }
    };

    const handleLogout = async () => {
        try {
            await authService.logout();
            setIsAuthenticated(false);
            setUserData(null);
            setMenuOpen(false);
        } catch (error) {
            console.error('Ошибка при выходе:', error);
        }
    };

    const closeModal = () => setActiveModal(null);

    const handleLoginSuccess = (user: UserType) => {
        setIsAuthenticated(true);
        setUserData(user);
        closeModal();
    };

    const handleRegisterSuccess = (user: UserType) => {
        setIsAuthenticated(true);
        setUserData(user);
        closeModal();
    };

    const handleRecoverySuccess = () => {
        setActiveModal('password-reset');
    };

    const handlePasswordResetSuccess = (user: UserType) => {
        setIsAuthenticated(true);
        setUserData(user);
        closeModal();
    };

    if (isLoading) {
        return (
            <div className={`${s.user} ${className}`}>
                <div className={s.loading}>Загрузка...</div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return (
            <div className={`${s.user} ${className}`}>
                <button onClick={() => setActiveModal('login')} className={s.auth_button}>
                    Вход
                </button>
                <button onClick={() => setActiveModal('register')} className={s.auth_button}>
                    Регистрация
                </button>

                {activeModal === 'login' && (
                    <LoginModal
                        onClose={closeModal}
                        onSwitchToRecovery={() => setActiveModal('recovery')}
                        onSuccess={handleLoginSuccess}
                    />
                )}

                {activeModal === 'register' && (
                    <RegisterModal
                        onClose={closeModal}
                        onSuccess={handleRegisterSuccess}
                    />
                )}

                {activeModal === 'recovery' && (
                    <RecoveryModal
                        onClose={closeModal}
                        onSwitchToLogin={() => setActiveModal('login')}
                        onSuccess={handleRecoverySuccess}
                    />
                )}

                {activeModal === 'password-reset' && (
                    <PasswordResetModal
                        onClose={closeModal}
                        onSuccess={handlePasswordResetSuccess}
                    />
                )}
            </div>
        );
    }

    return (
        <div className={`${s.user} ${className}`}>
            <div className={s.user_trigger} onClick={() => setMenuOpen(!menuOpen)}>
                <div className={s.avatar} />
                <div className={s.user_info}>
                    <div className={s.name}>{userData?.nickname || 'Пользователь'}</div>
                    <div className={s.info}>@{userData?.login}</div>
                </div>
            </div>

            {menuOpen && (
                <div className={s.dropdown} ref={menuRef}>
                    <button onClick={handleLogout} className={s.logout_button}>
                        Выйти
                    </button>
                </div>
            )}
        </div>
    );
};

export default User;
