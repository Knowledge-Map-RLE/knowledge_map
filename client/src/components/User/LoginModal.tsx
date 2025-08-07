import { useState } from 'react'
import s from './Modal.module.css'
import { authService, User } from '../../services/auth'

interface LoginModalProps {
    onClose: () => void
    onSwitchToRecovery: () => void
    onSuccess: (user: User) => void
}

export default function LoginModal({ onClose, onSwitchToRecovery, onSuccess }: LoginModalProps) {
    const [formData, setFormData] = useState({
        username: '',
        password: '',
        captcha: ''
    })
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState('')

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsLoading(true)
        setError('')

        try {
            const result = await authService.login({
                login: formData.username,
                password: formData.password,
                captcha: formData.captcha
            })
            
            if (result.success && result.user) {
                onSuccess(result.user)
            } else {
                setError(result.message || 'Ошибка входа')
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Ошибка входа. Проверьте логин и пароль.')
        } finally {
            setIsLoading(false)
        }
    }

    const handleInputChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }))
    }

    return (
        <div className={s.overlay} onClick={onClose}>
            <div className={s.modal} onClick={e => e.stopPropagation()}>
                <div className={s.header}>
                    <h2>Вход в систему</h2>
                    <button onClick={onClose} className={s.close_button}>×</button>
                </div>

                <form onSubmit={handleSubmit} className={s.form}>
                    <div className={s.field}>
                        <label htmlFor="username">Логин *</label>
                        <input
                            id="username"
                            type="text"
                            value={formData.username}
                            onChange={(e) => handleInputChange('username', e.target.value)}
                            required
                            className={s.input}
                        />
                    </div>

                    <div className={s.field}>
                        <label htmlFor="password">Пароль *</label>
                        <input
                            id="password"
                            type="password"
                            value={formData.password}
                            onChange={(e) => handleInputChange('password', e.target.value)}
                            required
                            className={s.input}
                        />
                    </div>

                    <div className={s.field}>
                        <label htmlFor="captcha">Капча *</label>
                        <div className={s.captcha_container}>
                            <div className={s.captcha_image}>
                                {/* Здесь будет изображение капчи */}
                                <div className={s.captcha_placeholder}>CAPTCHA</div>
                            </div>
                            <input
                                id="captcha"
                                type="text"
                                value={formData.captcha}
                                onChange={(e) => handleInputChange('captcha', e.target.value)}
                                required
                                className={s.input}
                                placeholder="Введите код"
                            />
                        </div>
                    </div>

                    {error && <div className={s.error}>{error}</div>}

                    <div className={s.actions}>
                        <button
                            type="submit"
                            disabled={isLoading || !formData.username || !formData.password || !formData.captcha}
                            className={s.submit_button}
                        >
                            {isLoading ? 'Вход...' : 'Войти'}
                        </button>
                    </div>

                    <div className={s.recovery_link}>
                        <button
                            type="button"
                            onClick={onSwitchToRecovery}
                            className={s.link_button}
                        >
                            Забыли данные для входа?
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
} 