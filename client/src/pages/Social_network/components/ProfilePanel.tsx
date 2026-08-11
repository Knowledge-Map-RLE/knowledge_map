import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { MdEmail, MdSend, MdCall, MdLanguage, MdPerson } from 'react-icons/md';
import {
    ACCOUNT_MODAL_EVENT,
    decodeContacts,
    getMe,
    PROFILE_UPDATED_EVENT,
    socialImageUrl,
    type SocialContacts,
    type SocialUserProfile,
} from '../../../services/api/social';
import { useAuth } from '../../../entities/auth';
import { useToast } from '../../../shared/ui/Toast';
import { Wall } from './Wall';
import s from '../Social_network.module.css';

const CONTACT_DEFS: Array<{
    key: keyof SocialContacts;
    icon: ReactNode;
    href?: (v: string) => string;
}> = [
    { key: 'email', icon: <MdEmail />, href: (v) => `mailto:${v}` },
    { key: 'telegram', icon: <MdSend />, href: (v) => `https://t.me/${v.replace(/^@/, '')}` },
    { key: 'phone', icon: <MdCall />, href: (v) => `tel:${v.replace(/[^\d+]/g, '')}` },
    { key: 'website', icon: <MdLanguage />, href: (v) => (v.startsWith('http://') || v.startsWith('https://') ? v : `https://${v}`) },
];

function ContactsView({ contacts }: { contacts?: SocialUserProfile['contacts'] }) {
    const decoded = decodeContacts(contacts);
    const entries = Object.entries(decoded).filter(([, v]) => v && String(v).trim());
    if (entries.length === 0) return null;
    return (
        <div className={s.profileSection}>
            <div className={s.fieldLabel}>Контакты</div>
            <div className={s.contactsRow}>
                {entries.map(([key, value]) => {
                    const def = CONTACT_DEFS.find((d) => d.key === key);
                    const text = String(value);
                    const href = def?.href?.(text);
                    const inner = (
                        <>
                            <span>{def?.icon ?? '•'}</span>
                            <span>{text}</span>
                        </>
                    );
                    return href ? (
                        <a key={key} className={s.contactItem} href={href} target="_blank" rel="noreferrer">
                            {inner}
                        </a>
                    ) : (
                        <span key={key} className={s.contactItem}>{inner}</span>
                    );
                })}
            </div>
        </div>
    );
}

export function ProfilePanel() {
    const { error: toastError } = useToast();
    const { user, isAuthenticated, requestLogin } = useAuth();
    const [bio, setBio] = useState('');
    const [avatarKey, setAvatarKey] = useState('');
    const [contacts, setContacts] = useState<SocialContacts>({});
    const [nickname, setNickname] = useState('');
    const [login, setLogin] = useState('');
    const [friendCount, setFriendCount] = useState(0);
    const [communitiesCount, setCommunitiesCount] = useState(0);
    const [loading, setLoading] = useState(!isAuthenticated);

    const loadProfile = useCallback(async () => {
        try {
            const res = await getMe();
            setBio(res.profile?.bio ?? '');
            setAvatarKey(res.profile?.avatar_key ?? '');
            setContacts(decodeContacts(res.profile?.contacts));
            setNickname(res.profile?.nickname ?? '');
            setLogin(res.profile?.login ?? '');
            setFriendCount(res.profile?.friend_count ?? 0);
            setCommunitiesCount((res.communities ?? []).length);
        } catch (e) {
            toastError(e instanceof Error ? e.message : 'Ошибка загрузки профиля');
        } finally {
            setLoading(false);
        }
    }, [toastError]);

    useEffect(() => {
        if (!isAuthenticated) {
            setLoading(false);
            return;
        }
        setLoading(true);
        void loadProfile();
    }, [isAuthenticated, loadProfile]);

    useEffect(() => {
        const onProfileUpdated = () => void loadProfile();
        window.addEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
        return () => window.removeEventListener(PROFILE_UPDATED_EVENT, onProfileUpdated);
    }, [loadProfile]);

    const handleEdit = () => {
        window.dispatchEvent(new Event(ACCOUNT_MODAL_EVENT));
    };

    if (loading) return <div className={s.hint}>Загрузка…</div>;

    if (!isAuthenticated) {
        return (
            <div className={s.panel}>
                <div className={s.panelSection}>
                    <div className={s.panelTitle}>Профиль</div>
                    <div className={s.gateCard}>
                        <div className={s.gateText}>
                            Войдите или зарегистрируйтесь, чтобы видеть свой профиль.
                        </div>
                        <button className={s.primaryBtn} onClick={requestLogin}>Войти / Зарегистрироваться</button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className={s.panel}>
            <div className={s.panelSection}>
                <div className={s.panelTitle}>Профиль</div>
                <div className={s.card}>
                    <div className={s.profileHead}>
                        {avatarKey ? (
                            <img src={socialImageUrl(avatarKey)} alt="Аватар" className={s.profileAvatar} />
                        ) : (
                            <div className={s.profileAvatar}><MdPerson /></div>
                        )}
                        <div className={s.profileHeadInfo}>
                            <div className={s.cardName}>{nickname || 'Пользователь'}</div>
                            <div className={s.cardSub}>@{login}</div>
                            <div className={s.statsRow}>
                                <div className={s.stat}><b>{friendCount}</b> друзей</div>
                                <div className={s.stat}><b>{communitiesCount}</b> сообществ</div>
                            </div>
                        </div>
                    </div>

                    {bio && (
                        <div className={s.profileSection}>
                            <div className={s.fieldLabel}>О себе</div>
                            <div className={s.profileBio}>{bio}</div>
                        </div>
                    )}

                    <ContactsView contacts={contacts} />

                    <div className={s.profileActions}>
                        <button className={s.primaryBtn} onClick={handleEdit}>
                            Редактировать
                        </button>
                    </div>
                </div>

                <Wall uid={user?.uid ?? ''} isMe />
            </div>
        </div>
    );
}
