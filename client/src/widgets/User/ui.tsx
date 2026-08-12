import { useState, useEffect, useRef, useCallback } from 'react';
import { MdNotifications, MdSettings } from 'react-icons/md';
import s from './User.module.css';
import { LoginModal } from './components/LoginModal';
import { RegisterModal } from './components/RegisterModal';
import { RecoveryModal } from './components/RecoveryModal';
import { PasswordResetModal } from './components/PasswordResetModal';
import { AccountModal } from './components/AccountModal';
import { NotificationsPopup } from './components/NotificationsPopup';
import { useAuth, AUTH_LOGIN_EVENT } from '../../entities/auth';
import type { User as UserType } from '../../services/auth';
import type { ModalType, UserProps } from './model';
import { getUnreadCount, getMe, PROFILE_UPDATED_EVENT, ACCOUNT_MODAL_EVENT, socialImageUrl } from '../../services/api/social';

const User: React.FC<UserProps> = ({ className = '' }) => {
    const [activeModal, setActiveModal] = useState<ModalType>(null);
    const { user: userData, isAuthLoading, setUser, logout, refresh } = useAuth();
    const [menuOpen, setMenuOpen] = useState(false);
    const [notifOpen, setNotifOpen] = useState(false);
    const [accountOpen, setAccountOpen] = useState(false);
    const [unread, setUnread] = useState(0);
    const [avatarKey, setAvatarKey] = useState('');
    const menuRef = useRef<HTMLDivElement>(null);

    const loadAvatar = useCallback(async () => {
        if (!userData) {
            setAvatarKey('');
            return;
        }
        try {
            const res = await getMe();
            setAvatarKey(res.profile?.avatar_key ?? '');
        } catch {
            /* не критично */
        }
    }, [userData]);

    useEffect(() => {
        void loadAvatar();
    }, [loadAvatar]);

    useEffect(() => {
        const onProfileUpdated = () => void loadAvatar();
        window.addEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
        return () => window.removeEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
    }, [loadAvatar]);

    const refreshUnread = useCallback(async () => {
        if (!userData) return;
        try {
            const res = await getUnreadCount();
            setUnread(res.unread_count ?? 0);
        } catch {
            /* не критично */
        }
    }, [userData]);

    useEffect(() => {
        refreshUnread();
        const timer = window.setInterval(refreshUnread, 30000);
        return () => window.clearInterval(timer);
    }, [refreshUnread]);

    useEffect(() => {
        const openAuth = (e: Event) => {
            const detail = (e as CustomEvent).detail as { modal?: string } | undefined;
            const modal = detail?.modal === 'register' ? 'register' : 'login';
            setActiveModal(modal);
        };
        window.addEventListener(AUTH_LOGIN_EVENT, openAuth);
        return () => window.removeEventListener(AUTH_LOGIN_EVENT, openAuth);
    }, []);

    useEffect(() => {
        const openAccount = () => setAccountOpen(true);
        window.addEventListener(ACCOUNT_MODAL_EVENT, openAccount);
        return () => window.removeEventListener(ACCOUNT_MODAL_EVENT, openAccount);
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

    const handleLogout = async () => {
        try {
            await logout();
            setMenuOpen(false);
        } catch (error) {
            console.error('Ошибка при выходе:', error);
        }
    };

    const openNotifications = () => {
        setMenuOpen(false);
        setNotifOpen(true);
    };

    const closeNotifications = () => {
        setNotifOpen(false);
        void refreshUnread();
    };

    const closeModal = () => setActiveModal(null);

    const handleLoginSuccess = (user: UserType) => {
        setUser(user);
        closeModal();
    };

    const handleRegisterSuccess = (user: UserType) => {
        setUser(user);
        closeModal();
    };

    const handleRecoverySuccess = () => {
        setActiveModal('password-reset');
    };

    const handlePasswordResetSuccess = () => {
        void refresh();
        closeModal();
    };

    if (isAuthLoading) {
        return (
            <div className={`${s.user} ${className}`}>
                <div className={s.loading}>Загрузка...</div>
            </div>
        );
    }

    if (!userData) {
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
            <button className={s.bell_button} onClick={openNotifications} title="Уведомления">
                <MdNotifications />
                {unread > 0 && <span className={s.bell_badge}>{unread > 99 ? '99+' : unread}</span>}
            </button>

            {notifOpen && <NotificationsPopup onClose={closeNotifications} />}
            <div className={s.user_trigger} onClick={() => setMenuOpen(!menuOpen)}>
                <div className={s.avatar}>
                    {avatarKey && (
                        <img src={socialImageUrl(avatarKey)} alt="Аватар" className={s.avatar_img} />
                    )}
                </div>
                <div className={s.user_info}>
                    <div className={s.name}>{userData.nickname || 'Пользователь'}</div>
                    <div className={s.info}>@{userData.login}</div>
                </div>
            </div>

            {menuOpen && (
                <div className={s.dropdown} ref={menuRef}>
                    <button onClick={() => { setMenuOpen(false); setAccountOpen(true); }} className={s.menu_button}>
                        <MdSettings /> Личный кабинет
                    </button>
                    <button onClick={openNotifications} className={s.menu_button}>
                        <MdNotifications /> Уведомления
                        {unread > 0 && <span className={s.menu_badge}>{unread > 99 ? '99+' : unread}</span>}
                    </button>
                    <button onClick={handleLogout} className={s.logout_button}>
                        Выйти
                    </button>
                </div>
            )}

            {accountOpen && (
                <AccountModal myUid={userData.uid} onClose={() => setAccountOpen(false)} />
            )}
        </div>
    );
};

export default User;
