import { useState } from 'react'
import s from './Modal.module.css'

interface PasswordResetModalProps {
    onClose: () => void
    onSuccess: (user: { username: string; displayName: string; level: number }) => void
}

export default function PasswordResetModal({ onClose, onSuccess }: PasswordResetModalProps) {
    const [formData, setFormData] = useState({
        newPassword: '',
        newPasswordConfirm: ''
    })
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState('')

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsLoading(true)
        setError('')

        if (formData.newPassword !== formData.newPasswordConfirm) {
            setError('Пароли не совпадают')
            setIsLoading(false)
            return
        }

        if (formData.newPassword.length < 8) {
            setError('Пароль должен содержать не менее 8 символов')
            setIsLoading(false)
            return
        }

        try {
            // Здесь будет вызов API для сброса пароля
            // Пока что симулируем успешный сброс
            await new Promise(resolve => setTimeout(resolve, 1000))
            
            onSuccess({
                username: 'user',
                displayName: 'Пользователь',
                level: 1
            })
        } catch (err) {
            setError('Ошибка сброса пароля')
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
                    <h2>Установка нового пароля</h2>
                    <button onClick={onClose} className={s.close_button}>×</button>
                </div>

                <div className={s.info}>
                    <p>Ключ восстановления подтвержден. Теперь установите новый пароль для вашего аккаунта.</p>
                    <p>Рекомендуется сохранить новый пароль в менеджере паролей, например <a href="https://bitwarden.com/" target="_blank" rel="noopener noreferrer" className={s.link}>Bitwarden</a>.</p>
                </div>

                <form onSubmit={handleSubmit} className={s.form}>
                    <div className={s.field}>
                        <label htmlFor="newPassword">Новый пароль *</label>
                        <input
                            id="newPassword"
                            type="password"
                            value={formData.newPassword}
                            onChange={(e) => handleInputChange('newPassword', e.target.value)}
                            required
                            minLength={8}
                            className={s.input}
                        />
                        <small className={s.hint}>Минимум 8 символов</small>
                    </div>

                    <div className={s.field}>
                        <label htmlFor="newPasswordConfirm">Подтверждение пароля *</label>
                        <input
                            id="newPasswordConfirm"
                            type="password"
                            value={formData.newPasswordConfirm}
                            onChange={(e) => handleInputChange('newPasswordConfirm', e.target.value)}
                            required
                            className={s.input}
                        />
                    </div>

                    {error && <div className={s.error}>{error}</div>}

                    <div className={s.actions}>
                        <button
                            type="submit"
                            disabled={isLoading || !formData.newPassword || !formData.newPasswordConfirm}
                            className={s.submit_button}
                        >
                            {isLoading ? 'Сохранение...' : 'Сохранить пароль'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
} 