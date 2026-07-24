import { useState } from 'react';
import s from './Modal.module.css';
import { authService } from '../../../services/auth';
import type { User } from '../../../entities/user';

interface RegisterModalProps {
    onClose: () => void;
    onSuccess: (user: User) => void;
}

export const RegisterModal: React.FC<RegisterModalProps> = ({ onClose, onSuccess }) => {
    const [formData, setFormData] = useState({
        username: '',
        password: '',
        passwordConfirm: '',
        displayName: '',
        captcha: ''
    });
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');

        if (formData.password !== formData.passwordConfirm) {
            setError('Пароли не совпадают');
            setIsLoading(false);
            return;
        }

        if (formData.password.length < 8) {
            setError('Пароль должен содержать не менее 8 символов');
            setIsLoading(false);
            return;
        }

        try {
            const registerResult = await authService.register({
                login: formData.username,
                password: formData.password,
                nickname: formData.displayName,
                captcha: formData.captcha,
            });

            if (!registerResult.success) {
                setError(registerResult.message || 'Ошибка регистрации');
                setIsLoading(false);
                return;
            }

            const loginResult = await authService.login({
                login: formData.username,
                password: formData.password,
                captcha: formData.captcha,
            });

            if (!loginResult.success || !loginResult.user) {
                setError(loginResult.message || 'Ошибка автоматического входа');
                setIsLoading(false);
                return;
            }

            onSuccess(loginResult.user);
        } catch {
            setError('Ошибка регистрации. Возможно, такой логин уже существует.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const isFormValid = formData.username && formData.password &&
                        formData.passwordConfirm && formData.displayName && formData.captcha;

    return (
        <div className={s.overlay} onClick={onClose}>
            <div className={s.modal} onClick={e => e.stopPropagation()}>
                <div className={s.header}>
                    <h2>Регистрация</h2>
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
                        <label htmlFor="displayName">Отображаемое имя *</label>
                        <input
                            id="displayName"
                            type="text"
                            value={formData.displayName}
                            onChange={(e) => handleInputChange('displayName', e.target.value)}
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
                            minLength={8}
                            className={s.input}
                        />
                        <small className={s.hint}>Минимум 8 символов</small>
                    </div>

                    <div className={s.field}>
                        <label htmlFor="passwordConfirm">Подтверждение пароля *</label>
                        <input
                            id="passwordConfirm"
                            type="password"
                            value={formData.passwordConfirm}
                            onChange={(e) => handleInputChange('passwordConfirm', e.target.value)}
                            required
                            className={s.input}
                        />
                    </div>

                    <div className={s.field}>
                        <label htmlFor="captcha">Капча *</label>
                        <div className={s.captcha_container}>
                            <div className={s.captcha_image}>
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
                            disabled={isLoading || !isFormValid}
                            className={s.submit_button}
                        >
                            {isLoading ? 'Регистрация...' : 'Зарегистрироваться'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
