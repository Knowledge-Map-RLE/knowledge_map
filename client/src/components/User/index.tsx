import { useState, useEffect } from 'react'
import s from './User.module.css'
import LoginModal from './LoginModal'
import RegisterModal from './RegisterModal'
import RecoveryModal from './RecoveryModal'
import PasswordResetModal from './PasswordResetModal'
import { authService, User as UserType } from '../../services/auth'

export type ModalType = 'login' | 'register' | 'recovery' | 'password-reset' | null

export default function User({ className='' }: { className: string }) {
    const [activeModal, setActiveModal] = useState<ModalType>(null)
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    const [userData, setUserData] = useState<UserType | null>(null)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        // Проверяем токен при загрузке компонента
        checkAuthStatus()
    }, [])

    const checkAuthStatus = async () => {
        try {
            const user = await authService.verifyToken()
            if (user) {
                setIsAuthenticated(true)
                setUserData(user)
            } else {
                setIsAuthenticated(false)
                setUserData(null)
            }
        } catch (error) {
            setIsAuthenticated(false)
            setUserData(null)
        } finally {
            setIsLoading(false)
        }
    }

    const handleLogin = () => setActiveModal('login')
    const handleRegister = () => setActiveModal('register')
    
    const handleLogout = async () => {
        try {
            await authService.logout()
            setIsAuthenticated(false)
            setUserData(null)
        } catch (error) {
            console.error('Ошибка при выходе:', error)
        }
    }

    const closeModal = () => setActiveModal(null)

    const handleLoginSuccess = (user: UserType) => {
        setIsAuthenticated(true)
        setUserData(user)
        closeModal()
    }

    const handleRegisterSuccess = (user: UserType) => {
        setIsAuthenticated(true)
        setUserData(user)
        closeModal()
    }

    const handleRecoverySuccess = () => {
        setActiveModal('password-reset')
    }

    const handlePasswordResetSuccess = (user: UserType) => {
        setIsAuthenticated(true)
        setUserData(user)
        closeModal()
    }

    if (isLoading) {
        return (
            <div className={`${s.user} ${className}`}>
                <div className={s.loading}>Загрузка...</div>
            </div>
        )
    }

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
        )
    }

    // Если пользователь авторизован, показываем информацию о пользователе
    return (
        <div className={`${s.user} ${className}`}>
            <div className={s.avatar}></div>
            <div className={s.user_info}>
                <div className={s.name}>{userData?.nickname || 'Пользователь'}</div>
                <div className={s.info}>@{userData?.login}</div>
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