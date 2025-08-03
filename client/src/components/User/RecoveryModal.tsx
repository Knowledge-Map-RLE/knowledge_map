import { useState } from 'react'
import s from './Modal.module.css'

interface RecoveryModalProps {
    onClose: () => void
    onSwitchToLogin: () => void
    onSuccess: () => void
}

export default function RecoveryModal({ onClose, onSwitchToLogin, onSuccess }: RecoveryModalProps) {
    const [formData, setFormData] = useState({
        recoveryKey: '',
        captcha: ''
    })
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState('')

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsLoading(true)
        setError('')

        try {
            // Здесь будет вызов API для проверки ключа восстановления
            // Пока что симулируем успешную проверку
            await new Promise(resolve => setTimeout(resolve, 1000))
            
            onSuccess()
        } catch (err) {
            setError('Неверный ключ восстановления или капча')
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
                    <h2>Восстановление доступа</h2>
                    <button onClick={onClose} className={s.close_button}>×</button>
                </div>

                <div className={s.info}>
                    <p>Введите ключ восстановления, который вы получили при регистрации.</p>
                    <p>Рекомендуется сохранить его в менеджере паролей, например <a href="https://bitwarden.com/" target="_blank" rel="noopener noreferrer" className={s.link}>Bitwarden</a>.</p>
                </div>

                <form onSubmit={handleSubmit} className={s.form}>
                    <div className={s.field}>
                        <label htmlFor="recoveryKey">Ключ восстановления *</label>
                        <input
                            id="recoveryKey"
                            type="text"
                            value={formData.recoveryKey}
                            onChange={(e) => handleInputChange('recoveryKey', e.target.value)}
                            required
                            className={s.input}
                            placeholder="Введите ключ восстановления"
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
                            disabled={isLoading || !formData.recoveryKey || !formData.captcha}
                            className={s.submit_button}
                        >
                            {isLoading ? 'Проверка...' : 'Проверить ключ'}
                        </button>
                    </div>

                    <div className={s.back_link}>
                        <button
                            type="button"
                            onClick={onSwitchToLogin}
                            className={s.link_button}
                        >
                            ← Вернуться к входу
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
} 