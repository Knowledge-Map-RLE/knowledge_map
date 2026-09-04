import { useCallback, useState } from 'react';
import { useRequireAuth } from '../../shared/hooks/useRequireAuth';
import { FeedbackButton } from './components/FeedbackButton';
import { FeedbackChat } from './components/FeedbackChat';

interface FeedbackProps {
    className?: string;
}

const Feedback: React.FC<FeedbackProps> = ({ className = '' }) => {
    const [open, setOpen] = useState(false);
    const requireAuth = useRequireAuth();

    const handleOpen = useCallback(() => {
        if (!requireAuth('Войдите или зарегистрируйтесь, чтобы отправить сообщение')) {
            return;
        }
        setOpen(true);
    }, [requireAuth]);

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
