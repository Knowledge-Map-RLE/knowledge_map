import { useState } from 'react';
import { MdArrowBack } from 'react-icons/md';
import s from './Modal.module.css';
import { ModalPortal } from '../../../shared/ui/ModalPortal';

interface RecoveryModalProps {
    onClose: () => void;
    onSwitchToLogin: () => void;
    onSuccess: () => void;
}

export const RecoveryModal: React.FC<RecoveryModalProps> = ({ onClose, onSwitchToLogin, onSuccess }) => {
    const [formData, setFormData] = useState({
        recoveryKey: '',
        captcha: ''
    });
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');

        try {
            await new Promise(resolve => setTimeout(resolve, 1000));
            onSuccess();
        } catch {
            setError('Неверный ключ восстановления или капча');
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const isFormValid = formData.recoveryKey && formData.captcha;

    return (
        <ModalPortal>
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
                            {isLoading ? 'Проверка...' : 'Проверить ключ'}
                        </button>
                    </div>

                    <div className={s.back_link}>
                        <button
                            type="button"
                            onClick={onSwitchToLogin}
                            className={s.link_button}
                        >
                            <MdArrowBack /> Вернуться к входу
                        </button>
                    </div>
                </form>
            </div>
        </div>
        </ModalPortal>
    );
};
