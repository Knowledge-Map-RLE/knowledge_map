import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MdToken } from 'react-icons/md';
import { useAuth } from '../../../entities/auth';
import { fetchSubscription, type SubscriptionState } from '../../../services/api/billing';
import { ACCOUNT_SUBSCRIPTION_EVENT } from '../../../services/api/social';
import s from '../Header.module.css';

function formatTokens(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`;
    return String(n);
}

const SubscriptionBadge: React.FC<{ className?: string }> = ({ className = '' }) => {
    const { user, isAuthLoading } = useAuth();
    const [sub, setSub] = useState<SubscriptionState | null>(null);

    useEffect(() => {
        if (!user) return;
        fetchSubscription().then(setSub).catch(() => {});
    }, [user]);

    if (isAuthLoading) return null;

    const handleClick = (e: React.MouseEvent) => {
        if (!user) return;
        e.preventDefault();
        window.dispatchEvent(new Event(ACCOUNT_SUBSCRIPTION_EVENT));
    };

    const isActive = sub?.active && sub.token_balance > 0;
    const tokenText = isActive ? `${formatTokens(sub.token_balance)} ток.` : null;

    if (!user || !isActive) {
        return (
            <Link to="/subscription" className={`${s.badge} ${s.badgeLink} ${className}`}>
                <MdToken className={s.badgeIcon} />
                <span className={s.badgeText}>Купи токены для ИИ функций</span>
            </Link>
        );
    }

    return (
        <button type="button" onClick={handleClick} className={`${s.badge} ${s.badgeClickable} ${className}`}>
            <MdToken className={s.badgeIcon} />
            <span className={s.badgeText}>{tokenText}</span>
        </button>
    );
};

export default SubscriptionBadge;
