import { MdBugReport } from 'react-icons/md';
import s from './FeedbackButton.module.css';
import { useTranslation } from 'react-i18next';

interface FeedbackButtonProps {
    onClick: () => void;
    hasActiveTicket?: boolean;
}

export function FeedbackButton({ onClick, hasActiveTicket = false }: FeedbackButtonProps) {
    const { t } = useTranslation();
    return (
        <button
            className={`${s.button} ${hasActiveTicket ? s.active : ''}`}
            onClick={onClick}
            title={t('header.feedback.title')}
            type="button"
        >
            <MdBugReport className={s.icon} />
            <span className={s.label}>{t('header.feedback.title')}</span>
        </button>
    );
}
