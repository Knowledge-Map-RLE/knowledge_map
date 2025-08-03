import { useState } from 'react'
import s from './User.module.css'
import { LoginModal, RegisterModal, RecoveryModal, PasswordResetModal } from './modals'

export type ModalType = 'login' | 'register' | 'recovery' | 'password-reset' | null

export default function User({ className='' }: { className: string }) {
    const [activeModal, setActiveModal] = useState<ModalType>(null)
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    const [userData, setUserData] = useState<{
        username: string
        displayName: string
        level: number
    } | null>(null)

    const handleLogin = () => setActiveModal('login')
    const handleRegister = () => setActiveModal('register')
    const handleLogout = () => {
        setIsAuthenticated(false)
        setUserData(null)
        // Здесь будет вызов API для выхода
    }

    const closeModal = () => setActiveModal(null)

    // Если пользователь не авторизован, показываем кнопки входа/регистрации
    if (!isAuthenticated) {
        return (
            <div className={`${s.user} ${className}`}>
                <div className={s.auth_buttons}>
                    <button 
                        onClick={handleLogin}
                        className={s.auth_button}
                    >
                        Вход
                    </button>
                    <button 
                        onClick={handleRegister}
                        className={s.auth_button}
                    >
                        Регистрация
                    </button>
                </div>

                {/* Модальные окна */}
                {activeModal === 'login' && (
                    <LoginModal 
                        onClose={closeModal}
                        onSwitchToRecovery={() => setActiveModal('recovery')}
                        onSuccess={(user) => {
                            setIsAuthenticated(true)
                            setUserData(user)
                            closeModal()
                        }}
                    />
                )}

                {activeModal === 'register' && (
                    <RegisterModal 
                        onClose={closeModal}
                        onSuccess={(user) => {
                            setIsAuthenticated(true)
                            setUserData(user)
                            closeModal()
                        }}
                    />
                )}

                {activeModal === 'recovery' && (
                    <RecoveryModal 
                        onClose={closeModal}
                        onSwitchToLogin={() => setActiveModal('login')}
                        onSuccess={() => setActiveModal('password-reset')}
                    />
                )}

                {activeModal === 'password-reset' && (
                    <PasswordResetModal 
                        onClose={closeModal}
                        onSuccess={(user) => {
                            setIsAuthenticated(true)
                            setUserData(user)
                            closeModal()
                        }}
                    />
                )}
            </div>
        )
    }

    // Если пользователь авторизован, показываем информацию о пользователе
    return (
        <div className={`${s.user} ${className}`}>
            <div className={s.avatar}></div>
            <div className={s.user_info}>
                <div className={s.name}>{userData?.displayName || 'Пользователь'}</div>
                <div className={s.info}>УР: {userData?.level || 0} | @{userData?.username}</div>
            </div>
            <button 
                onClick={handleLogout}
                className={s.logout_button}
            >
                Выйти
            </button>
        </div>
    )
}