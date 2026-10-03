import { useCallback, useState } from 'react';
import { useRequireAuth } from '../../shared/hooks/useRequireAuth';
import { FeedbackButton } from './components/FeedbackButton';
import { FeedbackChat } from './components/FeedbackChat';
import { useTranslation } from 'react-i18next';

interface FeedbackProps {
    className?: string;
}

const Feedback: React.FC<FeedbackProps> = ({ className = '' }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const requireAuth = useRequireAuth();

    const handleOpen = useCallback(() => {
        if (!requireAuth(t('header.feedback.loginRequired'))) {
            return;
        }
        setOpen(true);
    }, [requireAuth, t]);

    const handleClose = useCallback(() => {
        setOpen(false);
    }, []);

    return (
        <>
            <div className={className}>
                <FeedbackButton onClick={handleOpen} />
            </div>
            {open && <FeedbackChat onClose={handleClose} />}
        </>
    );
};

export default Feedback;
