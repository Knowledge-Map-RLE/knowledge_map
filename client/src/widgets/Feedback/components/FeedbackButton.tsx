import { MdBugReport } from 'react-icons/md';
import s from './FeedbackButton.module.css';

interface FeedbackButtonProps {
    onClick: () => void;
    hasActiveTicket?: boolean;
}

export function FeedbackButton({ onClick, hasActiveTicket = false }: FeedbackButtonProps) {
    return (
        <button
            className={`${s.button} ${hasActiveTicket ? s.active : ''}`}
            onClick={onClick}
            title="Баг? Пожелание?"
            type="button"
        >
            <MdBugReport className={s.icon} />
            <span className={s.label}>Баг? Пожеление?</span>
        </button>
    );
}
